import struct
import tempfile
import unittest
from pathlib import Path

from ra3_auto.sage import (
    ASSET_ENTRY,
    MANIFEST_HEADER,
    MANIFEST_HEADER_V7,
    AssetEntryData,
    BigArchive,
    LinkedAssetData,
    ManifestData,
    build_big,
    build_linked_stream,
    binary_asset_builder_output_checksum,
    convert_manifest_version,
    derive_modified_instance_hash,
    extract_linked_assets,
    extract_linked_patch_assets,
    fast_hash,
    reconstruct_linked_patch_chain,
    rebase_patch_manifest,
    refpack_decompress,
    validate_linked_stream,
)


def make_manifest(
    entries,
    references=((2, "static.manifest"),),
    checksum=0x12345678,
    linked=1,
    version=6,
):
    asset_names = bytearray()
    source_names = bytearray()
    packed_entries = bytearray()
    for index, entry in enumerate(entries):
        name_offset = len(asset_names)
        source_offset = len(source_names)
        asset_names.extend(f"Asset{index}".encode("ascii") + b"\0")
        source_names.extend(f"source{index}.xml".encode("ascii") + b"\0")
        packed_entries.extend(
            ASSET_ENTRY.pack(
                entry[0],
                entry[1],
                entry[2],
                entry[3],
                0,
                0,
                name_offset,
                source_offset,
                entry[4],
                entry[5],
                entry[6],
                0,
            )
        )
    reference_buffer = b"".join(
        bytes((kind,)) + name.encode("ascii") + b"\0" for kind, name in references
    )
    instance_sizes = [entry[4] for entry in entries]
    relocation_sizes = [entry[5] for entry in entries]
    imports_sizes = [entry[6] for entry in entries]
    fields = (
        checksum,
        0x54EEE764,
        len(entries),
        sum(instance_sizes),
        max(instance_sizes, default=0),
        max(relocation_sizes, default=0),
        max(imports_sizes, default=0),
        0,
        len(reference_buffer),
        len(asset_names),
        len(source_names),
    )
    if version == 6:
        header = MANIFEST_HEADER.pack(0, linked, version, *fields)
    elif version == 7:
        header = MANIFEST_HEADER_V7.pack(0, version, 0, linked, *fields)
    else:
        raise ValueError(version)
    return bytes(header + packed_entries + reference_buffer + asset_names + source_names)


class RefPackTests(unittest.TestCase):
    def test_literal_commands(self):
        payload = b"\x10\xfb\x00\x00\x05\xe0hell\xfdo"
        self.assertEqual(refpack_decompress(payload), b"hello")

    def test_uncompressed_input_is_unchanged(self):
        self.assertEqual(refpack_decompress(b"plain"), b"plain")


class FastHashTests(unittest.TestCase):
    def test_known_symbol_hashes(self):
        self.assertEqual(fast_hash(b"AIStrategicStateDefinition"), 0x242FF6D4)
        self.assertEqual(fast_hash(b"sovietexpansion_brutal"), 0xD0C88B65)

    def test_bab_checksum_uses_memory_stream_capacity(self):
        entry = AssetEntryData(
            0x242FF6D4,
            0xD0C88B65,
            0xD63DE874,
            0x6C3EFE4E,
            0,
            2,
            0,
            0,
            412,
            56,
            12,
            0,
        )
        self.assertEqual(binary_asset_builder_output_checksum([entry]), 0x8DD56589)

    def test_modified_instance_hash_is_stable_and_non_stock(self):
        first = derive_modified_instance_hash(123, b"payload", purpose="test")
        second = derive_modified_instance_hash(123, b"payload", purpose="test")
        self.assertEqual(first, second)
        self.assertNotEqual(first, 123)


class ManifestTests(unittest.TestCase):
    def test_manifest_version_conversion_preserves_entries_and_buffers(self):
        original = make_manifest(
            [(1, 2, 3, 4, 8, 4, 0)],
            references=((1, "global.manifest"),),
            version=7,
        )
        as_v6 = convert_manifest_version(original, 6, all_types_hash=0x54EEE764)
        round_trip = convert_manifest_version(as_v6, 7)
        parsed_original = ManifestData.parse(original)
        parsed_v6 = ManifestData.parse(as_v6)
        parsed_round_trip = ManifestData.parse(round_trip)
        self.assertEqual(parsed_v6.header.version, 6)
        self.assertEqual(parsed_v6.header.all_types_hash, 0x54EEE764)
        self.assertEqual(parsed_round_trip.header.version, 7)
        self.assertEqual(parsed_v6.entries, parsed_original.entries)
        self.assertEqual(parsed_v6.reference_manifests, ((1, "global.manifest"),))
        self.assertEqual(
            as_v6[parsed_v6.asset_entries_offset :],
            original[parsed_original.asset_entries_offset :],
        )

    def test_rebase_inherited_hashes_and_reference(self):
        compile_base = make_manifest(
            [
                (1, 11, 999, 998, 50, 60, 70),
                (1, 12, 102, 202, 20, 30, 40),
            ],
            linked=0,
        )
        retail = make_manifest(
            [
                (1, 11, 101, 201, 0, 0, 0),
                (1, 12, 102, 202, 0, 0, 0),
            ]
        )
        mod = make_manifest(
            [
                (1, 11, 999, 998, 50, 60, 70),
                (1, 12, 777, 776, 3, 0, 0),
                (1, 13, 555, 554, 2, 0, 0),
            ],
            references=(
                (2, "static.manifest"),
                (1, "sagexml\\static.manifest"),
                (1, "sagexml\\global.manifest"),
            ),
        )

        rebased, stats = rebase_patch_manifest(
            mod,
            compile_base,
            retail,
            "static.12.manifest",
        )
        parsed = ManifestData.parse(rebased)
        self.assertEqual(
            parsed.reference_manifests,
            (
                (2, "static.12.manifest"),
                (1, "sagexml\\static.manifest"),
                (1, "sagexml\\global.manifest"),
            ),
        )
        self.assertEqual(parsed.entries[0].type_hash, 101)
        self.assertEqual(parsed.entries[0].instance_hash, 201)
        self.assertEqual(parsed.entries[1].type_hash, 777)
        self.assertEqual(stats.inherited_assets, 1)
        self.assertEqual(stats.changed_existing_assets, 1)
        self.assertEqual(stats.new_assets, 1)

    def test_zero_sized_new_asset_is_counted_as_new(self):
        compile_base = make_manifest([(1, 11, 101, 201, 0, 0, 0)])
        retail = make_manifest([(1, 11, 101, 201, 0, 0, 0)])
        mod = make_manifest([(1, 99, 999, 998, 0, 0, 0)])
        _, stats = rebase_patch_manifest(
            mod,
            compile_base,
            retail,
            "static.12.manifest",
        )
        self.assertEqual(stats.new_assets, 1)

    def test_inherited_asset_missing_from_retail_is_rejected(self):
        compile_base = make_manifest([(1, 99, 999, 998, 5, 6, 7)])
        retail = make_manifest([])
        mod = make_manifest([(1, 99, 999, 998, 5, 6, 7)])
        with self.assertRaisesRegex(ValueError, "absent from the retail base"):
            rebase_patch_manifest(
                mod,
                compile_base,
                retail,
                "static.12.manifest",
            )

    def test_multiple_patch_base_references_are_rejected(self):
        compile_base = make_manifest([(1, 11, 101, 201, 0, 0, 0)])
        retail = make_manifest([(1, 11, 101, 201, 0, 0, 0)])
        mod = make_manifest(
            [(1, 11, 101, 201, 0, 0, 0)],
            references=((2, "global.manifest"), (2, "global.5.manifest")),
        )
        with self.assertRaisesRegex(ValueError, "multiple patch-base"):
            rebase_patch_manifest(
                mod,
                compile_base,
                retail,
                "global.12.manifest",
            )

    def test_linked_stream_lengths_and_checksums(self):
        manifest = make_manifest([(1, 11, 101, 201, 3, 4, 8)])
        checksum = struct.pack("<I", 0x12345678)
        validate_linked_stream(
            manifest,
            checksum + b"abc",
            checksum + b"12345678",
            checksum + b"1234",
        )
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            validate_linked_stream(
                manifest,
                checksum + b"ab",
                checksum + b"12345678",
                checksum + b"1234",
            )

    def test_version_7_manifest_and_stream_preamble(self):
        manifest = make_manifest(
            [(1, 11, 101, 201, 3, 4, 8)],
            references=((1, "global.manifest"),),
            version=7,
        )
        parsed = ManifestData.parse(manifest)
        self.assertEqual(parsed.header.version, 7)
        self.assertEqual(parsed.asset_entries_offset, MANIFEST_HEADER_V7.size)
        self.assertEqual(parsed.reference_manifests, ((1, "global.manifest"),))

        checksum = struct.pack("<I", 0x12345678)
        validate_linked_stream(
            manifest,
            b"\x00\x00\xbb\xba" + checksum + b"abc",
            b"\x00\x00\xb1\xba" + checksum + b"12345678",
            b"\x00\x00\xbe\xba" + checksum + b"1234",
        )

    def test_linked_stream_excludes_inherited_nonzero_chunks(self):
        compile_base = make_manifest(
            [
                (1, 11, 101, 201, 50, 60, 70),
                (1, 12, 102, 202, 20, 30, 40),
            ],
            linked=0,
        )
        manifest = make_manifest(
            [
                (1, 11, 101, 201, 50, 60, 70),
                (1, 12, 777, 776, 3, 4, 8),
                (1, 13, 555, 554, 2, 1, 2),
            ]
        )
        checksum = struct.pack("<I", 0x12345678)
        validate_linked_stream(
            manifest,
            checksum + b"abcde",
            checksum + b"1234567890",
            checksum + b"12345",
            compile_base,
        )

    def test_version_7_linked_stream_round_trip(self):
        original = LinkedAssetData(
            entry=AssetEntryData(
                type_id=0x11111111,
                instance_id=0x22222222,
                type_hash=0x33333333,
                instance_hash=0x44444444,
                asset_reference_offset=123,
                asset_reference_count=99,
                name_offset=123,
                source_file_name_offset=456,
                instance_data_size=999,
                relocation_data_size=999,
                imports_data_size=999,
                tokenized=0,
            ),
            asset_references=struct.pack("<II", 7, 8),
            name="AIStrategicStateDefinition:Probe",
            source_file_name="DATA:UV/Data/S.xml",
            instance_data=b"instance",
            imports_data=b"imports",
            relocation_data=b"relocations",
        )
        stream = build_linked_stream(
            [original],
            version=7,
            stream_checksum=0x85FE7DA0,
            all_types_hash=0x5454A8E9,
            reference_manifests=((1, "global.manifest"),),
        )
        parsed = ManifestData.parse(stream.manifest)
        self.assertEqual(parsed.header.version, 7)
        self.assertEqual(parsed.header.asset_count, 1)
        self.assertEqual(parsed.header.total_instance_data_size, len(b"instance"))
        self.assertEqual(parsed.reference_manifests, ((1, "global.manifest"),))
        extracted = extract_linked_assets(
            stream.manifest,
            stream.binary,
            stream.imports,
            stream.relocations,
        )
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].entry.key, original.entry.key)
        self.assertEqual(extracted[0].entry.instance_hash, 0x44444444)
        self.assertEqual(extracted[0].asset_references, original.asset_references)
        self.assertEqual(extracted[0].name, original.name)
        self.assertEqual(extracted[0].source_file_name, original.source_file_name)
        self.assertEqual(extracted[0].instance_data, original.instance_data)
        self.assertEqual(extracted[0].imports_data, original.imports_data)
        self.assertEqual(extracted[0].relocation_data, original.relocation_data)

    def test_zero_asset_version_7_stream_is_valid(self):
        stream = build_linked_stream(
            [],
            version=7,
            stream_checksum=0x85FE7DA0,
            all_types_hash=0x5454A8E9,
            reference_manifests=(
                (1, "static.manifest"),
                (1, "global.manifest"),
                (1, "audio.manifest"),
            ),
        )
        parsed = ManifestData.parse(stream.manifest)
        self.assertEqual(parsed.header.asset_count, 0)
        self.assertEqual(len(stream.binary), 8)
        self.assertEqual(len(stream.imports), 8)
        self.assertEqual(len(stream.relocations), 8)

    def test_duplicate_linked_asset_ids_are_rejected(self):
        asset = LinkedAssetData(
            entry=AssetEntryData(1, 2, 3, 4, 0, 0, 0, 0, 0, 0, 0, 0),
            asset_references=b"",
            name="Probe",
            source_file_name="probe.xml",
            instance_data=b"",
            imports_data=b"",
            relocation_data=b"",
        )
        with self.assertRaisesRegex(ValueError, "Duplicate linked asset ID"):
            build_linked_stream(
                [asset, asset],
                version=7,
                stream_checksum=1,
                all_types_hash=2,
            )

    def test_reconstructs_incremental_patch_with_schema_change_and_removal(self):
        def item(instance_id, instance_hash, payload, name, *, type_hash=30):
            return LinkedAssetData(
                entry=AssetEntryData(
                    1,
                    instance_id,
                    type_hash,
                    instance_hash,
                    0,
                    0,
                    0,
                    0,
                    len(payload),
                    0,
                    0,
                    0,
                ),
                asset_references=b"",
                name=name,
                source_file_name="retail.xml",
                instance_data=payload,
                imports_data=b"",
                relocation_data=b"",
            )

        inherited = item(10, 100, b"old-a", "A")
        changed_old = item(20, 200, b"old-b", "B")
        removed = item(40, 400, b"removed", "D")
        base_assets = (inherited, changed_old, removed)
        base_checksum = binary_asset_builder_output_checksum(
            [asset.entry for asset in base_assets]
        )
        base = build_linked_stream(
            base_assets,
            version=6,
            stream_checksum=base_checksum,
            all_types_hash=50,
            reference_manifests=((1, "audio.manifest"),),
        )

        inherited_with_new_type = LinkedAssetData(
            entry=AssetEntryData(
                1, 10, 31, 100, 0, 0, 0, 0, 5, 0, 0, 0
            ),
            asset_references=b"",
            name="A",
            source_file_name="retail.xml",
            instance_data=b"old-a",
            imports_data=b"",
            relocation_data=b"",
        )
        added = item(30, 300, b"new-c", "C", type_hash=31)
        changed_new = item(20, 201, b"new-b", "B", type_hash=31)
        current_assets = (inherited_with_new_type, added, changed_new)
        patch_checksum = binary_asset_builder_output_checksum(
            [asset.entry for asset in current_assets]
        )
        complete_patch_manifest = build_linked_stream(
            current_assets,
            version=6,
            stream_checksum=patch_checksum,
            all_types_hash=51,
            reference_manifests=(
                (2, "global.manifest"),
                (1, "audio.manifest"),
            ),
        ).manifest
        # A retail incremental manifest keeps the complete catalog but gives
        # inherited entries zero chunk sizes.  Its header totals remain the
        # fully materialized totals after the patch chain is resolved.
        patch_manifest = bytearray(complete_patch_manifest)
        patch_entries_offset = ManifestData.parse(
            complete_patch_manifest
        ).asset_entries_offset
        struct.pack_into("<III", patch_manifest, patch_entries_offset + 32, 0, 0, 0)
        checksum_prefix = struct.pack("<I", patch_checksum)
        patch = type(base)(
            manifest=bytes(patch_manifest),
            binary=checksum_prefix + added.instance_data + changed_new.instance_data,
            imports=checksum_prefix,
            relocations=checksum_prefix,
        )

        extracted_patch = extract_linked_patch_assets(
            patch.manifest,
            patch.binary,
            patch.imports,
            patch.relocations,
            base.manifest,
        )
        self.assertEqual([asset.name for asset in extracted_patch], ["C", "B"])

        rebuilt = reconstruct_linked_patch_chain(base, (patch,))
        rebuilt_manifest = ManifestData.parse(rebuilt.manifest)
        rebuilt_assets = extract_linked_assets(
            rebuilt.manifest,
            rebuilt.binary,
            rebuilt.imports,
            rebuilt.relocations,
        )
        self.assertEqual([asset.name for asset in rebuilt_assets], ["A", "C", "B"])
        self.assertEqual(
            [asset.instance_data for asset in rebuilt_assets],
            [b"old-a", b"new-c", b"new-b"],
        )
        self.assertEqual(rebuilt_assets[0].entry.type_hash, 31)
        self.assertEqual(rebuilt_manifest.header.all_types_hash, 51)
        self.assertEqual(rebuilt_manifest.header.stream_checksum, patch_checksum)
        self.assertEqual(
            rebuilt_manifest.reference_manifests,
            ((1, "audio.manifest"),),
        )

    def test_incremental_patch_rejects_truncated_payload(self):
        base_asset = LinkedAssetData(
            AssetEntryData(1, 2, 3, 4, 0, 0, 0, 0, 1, 0, 0, 0),
            b"",
            "Base",
            "base.xml",
            b"a",
            b"",
            b"",
        )
        base = build_linked_stream(
            (base_asset,), version=6, stream_checksum=10, all_types_hash=20
        )
        changed = LinkedAssetData(
            AssetEntryData(1, 2, 3, 5, 0, 0, 0, 0, 2, 0, 0, 0),
            b"",
            "Base",
            "base.xml",
            b"bb",
            b"",
            b"",
        )
        full_patch = build_linked_stream(
            (changed,), version=6, stream_checksum=11, all_types_hash=20
        )
        with self.assertRaisesRegex(ValueError, "patch length mismatch"):
            extract_linked_patch_assets(
                full_patch.manifest,
                struct.pack("<I", 11) + b"b",
                struct.pack("<I", 11),
                struct.pack("<I", 11),
                base.manifest,
            )


class BigArchiveTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.big"
            build_big(
                [
                    ("data/static.version", b".13"),
                    ("data/static.13.bin", b"payload"),
                ],
                path,
            )
            archive = BigArchive(path)
            self.assertEqual(
                [entry.name for entry in archive.entries],
                ["data\\static.version", "data\\static.13.bin"],
            )
            self.assertEqual(archive.read("DATA\\STATIC.13.BIN"), b"payload")

    def test_unsafe_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Unsafe BIG entry"):
                build_big([("..\\escape", b"x")], Path(directory) / "bad.big")

    def test_big_endian_archive_size_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.big"
            build_big([("data/payload.bin", b"payload")], path)
            raw = bytearray(path.read_bytes())
            struct.pack_into(">I", raw, 4, len(raw))
            path.write_bytes(raw)
            self.assertEqual(BigArchive(path).read("data\\payload.bin"), b"payload")


if __name__ == "__main__":
    unittest.main()
