"""Minimal SAGE BIG4 and linked-stream tooling used by RA3 Auto Enhance.

The game stores patch streams as a BIG archive containing a manifest plus
parallel binary, import, and relocation files.  This module intentionally
implements only the PC formats required by Red Alert 3 and Uprising.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import struct
from typing import Iterable, Sequence


BIG_HEADER_SIZE = 16
BIG_ENTRY = struct.Struct(">II")
MANIFEST_HEADER = struct.Struct("<BBH11I")
MANIFEST_HEADER_V7 = struct.Struct("<IHBB11I")
ASSET_ENTRY = struct.Struct("<12I")
STREAM_MAGIC_V7 = {
    "binary": b"\x00\x00\xbb\xba",
    "imports": b"\x00\x00\xb1\xba",
    "relocations": b"\x00\x00\xbe\xba",
}


@dataclass(frozen=True)
class BigEntry:
    name: str
    offset: int
    size: int


class BigArchive:
    """Read an unencrypted SAGE BIG4/BIGF archive."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._size = self.path.stat().st_size
        with self.path.open("rb") as stream:
            raw_header = stream.read(BIG_HEADER_SIZE)
            if len(raw_header) != BIG_HEADER_SIZE:
                raise ValueError(f"Truncated BIG header: {self.path}")
            magic = raw_header[:4]
            archive_size_little = struct.unpack_from("<I", raw_header, 4)[0]
            archive_size_big = struct.unpack_from(">I", raw_header, 4)[0]
            count, data_start = struct.unpack_from(">II", raw_header, 8)
            if magic not in (b"BIG4", b"BIGF"):
                raise ValueError(f"Unsupported BIG magic {magic!r}: {self.path}")
            archive_sizes = (
                archive_size_little,
                archive_size_big,
            )
            archive_size = next(
                (size for size in archive_sizes if size == self._size),
                next((size for size in archive_sizes if size <= self._size), 0),
            )
            if not archive_size or data_start > self._size:
                raise ValueError(f"Invalid BIG bounds: {self.path}")

            entries: list[BigEntry] = []
            by_name: dict[str, BigEntry] = {}
            for _ in range(count):
                raw_entry = stream.read(BIG_ENTRY.size)
                if len(raw_entry) != BIG_ENTRY.size:
                    raise ValueError(f"Truncated BIG entry table: {self.path}")
                offset, size = BIG_ENTRY.unpack(raw_entry)
                name_bytes = bytearray()
                while True:
                    byte = stream.read(1)
                    if not byte:
                        raise ValueError(f"Unterminated BIG entry name: {self.path}")
                    if byte == b"\0":
                        break
                    name_bytes.extend(byte)
                    if len(name_bytes) > 4096:
                        raise ValueError(f"Unreasonably long BIG entry name: {self.path}")
                name = name_bytes.decode("latin-1")
                if offset < data_start or offset + size > self._size:
                    raise ValueError(f"BIG entry is outside the archive: {name}")
                key = name.casefold()
                if key in by_name:
                    raise ValueError(f"Duplicate BIG entry name: {name}")
                entry = BigEntry(name=name, offset=offset, size=size)
                entries.append(entry)
                by_name[key] = entry

        self.magic = magic
        self.archive_size = archive_size
        self.data_start = data_start
        self.entries = tuple(entries)
        self._by_name = by_name

    def read(self, name: str, *, decompress: bool = True) -> bytes:
        entry = self._by_name.get(name.casefold())
        if entry is None:
            raise KeyError(name)
        with self.path.open("rb") as stream:
            stream.seek(entry.offset)
            data = stream.read(entry.size)
        if len(data) != entry.size:
            raise ValueError(f"Truncated BIG entry payload: {entry.name}")
        if decompress and is_refpack(data):
            return refpack_decompress(data)
        return data


def is_refpack(data: bytes) -> bool:
    return len(data) >= 5 and (data[0] & 0x3E) == 0x10 and data[1] == 0xFB


def refpack_decompress(data: bytes) -> bytes:
    """Decompress an EA RefPack payload."""

    if not is_refpack(data):
        return data

    output_size = (data[2] << 16) | (data[3] << 8) | data[4]
    size_width = 3
    if data[0] & 0x80:
        if len(data) < 6:
            raise ValueError("Truncated RefPack size header")
        output_size = (output_size << 8) | data[5]
        size_width = 4
    position = 2 + size_width * (2 if data[0] & 0x01 else 1)
    output = bytearray()

    def take(count: int) -> bytes:
        nonlocal position
        end = position + count
        if end > len(data):
            raise ValueError("Truncated RefPack command")
        value = data[position:end]
        position = end
        return value

    while len(output) < output_size:
        command = take(1)[0]
        if not command & 0x80:
            second = take(1)[0]
            literal_count = command & 0x03
            copy_count = ((command & 0x1C) >> 2) + 3
            reference = (
                len(output)
                + literal_count
                - 1
                - (second + ((command & 0x60) << 3))
            )
        elif not command & 0x40:
            second, third = take(2)
            literal_count = second >> 6
            copy_count = (command & 0x3F) + 4
            reference = (
                len(output)
                + literal_count
                - 1
                - (((second & 0x3F) << 8) + third)
            )
        elif not command & 0x20:
            second, third, fourth = take(3)
            literal_count = command & 0x03
            copy_count = ((command & 0x0C) << 6) + fourth + 5
            reference = (
                len(output)
                + literal_count
                - 1
                - (((command & 0x10) << 12) + (second << 8) + third)
            )
        else:
            literal_count = ((command & 0x1F) << 2) + 4
            if literal_count > 0x70:
                literal_count = command & 0x03
            output.extend(take(literal_count))
            if len(output) > output_size:
                raise ValueError("RefPack literal exceeds declared output size")
            continue

        output.extend(take(literal_count))
        for _ in range(copy_count):
            if reference < 0 or reference >= len(output):
                raise ValueError("Invalid RefPack back-reference")
            output.append(output[reference])
            reference += 1
        if len(output) > output_size:
            raise ValueError("RefPack command exceeds declared output size")

    return bytes(output)


def fast_hash(data: bytes | bytearray, seed: int | None = None) -> int:
    """Return the 32-bit SAGE/BinaryAssetBuilder FastHash value."""

    raw = memoryview(bytes(data))
    value = (len(raw) if seed is None else seed) & 0xFFFFFFFF
    full_length = len(raw) & ~3
    position = 0
    while position < full_length:
        first = int.from_bytes(raw[position : position + 2], "little")
        second = int.from_bytes(raw[position + 2 : position + 4], "little")
        value = (value + first) & 0xFFFFFFFF
        value ^= ((second ^ ((value << 5) & 0xFFFFFFFF)) << 11) & 0xFFFFFFFF
        value = (value + (value >> 11)) & 0xFFFFFFFF
        position += 4

    extra = len(raw) & 3
    if extra == 1:
        value = (value + raw[position]) & 0xFFFFFFFF
        value ^= (value << 10) & 0xFFFFFFFF
        value = (value + (value >> 1)) & 0xFFFFFFFF
    elif extra == 2:
        value = (
            value + int.from_bytes(raw[position : position + 2], "little")
        ) & 0xFFFFFFFF
        value ^= (value << 11) & 0xFFFFFFFF
        value = (value + (value >> 17)) & 0xFFFFFFFF
    elif extra == 3:
        value = (
            value + int.from_bytes(raw[position : position + 2], "little")
        ) & 0xFFFFFFFF
        value ^= (value << 16) & 0xFFFFFFFF
        value ^= (raw[position + 2] << 18) & 0xFFFFFFFF
        value = (value + (value >> 11)) & 0xFFFFFFFF

    value ^= (value << 3) & 0xFFFFFFFF
    value = (value + (value >> 5)) & 0xFFFFFFFF
    value ^= (value << 2) & 0xFFFFFFFF
    value = (value + (value >> 15)) & 0xFFFFFFFF
    value ^= (value << 10) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def binary_asset_builder_output_checksum(
    entries: Sequence[AssetEntryData],
) -> int:
    """Reproduce BinaryAssetBuilder's linked-stream output checksum.

    BAB hashes the complete capacity buffer of a default .NET MemoryStream,
    not merely its written length.  The buffer contains five uint32 values per
    output asset: type ID/hash, instance ID/hash, and reference count.
    """

    metadata = b"".join(
        struct.pack(
            "<IIIII",
            entry.type_id,
            entry.type_hash,
            entry.instance_id,
            entry.instance_hash,
            entry.asset_reference_count,
        )
        for entry in entries
    )
    if not metadata:
        return 0
    capacity = 256
    while capacity < len(metadata):
        capacity *= 2
    return fast_hash(metadata.ljust(capacity, b"\0"))


def derive_modified_instance_hash(
    original_hash: int,
    payload: bytes | bytearray,
    *,
    purpose: str,
) -> int:
    """Derive a stable non-stock instance hash for a manually patched asset."""

    if not purpose or "\0" in purpose:
        raise ValueError("A non-empty hash purpose is required")
    value = fast_hash(purpose.encode("utf-8") + b"\0" + bytes(payload), original_hash)
    if value == original_hash:
        value ^= 0xA5A5A5A5
    return value


@dataclass(frozen=True)
class ManifestHeaderData:
    big_endian: int
    linked: int
    version: int
    stream_checksum: int
    all_types_hash: int
    asset_count: int
    total_instance_data_size: int
    max_instance_chunk_size: int
    max_relocation_chunk_size: int
    max_imports_chunk_size: int
    asset_reference_buffer_size: int
    reference_manifest_name_buffer_size: int
    asset_name_buffer_size: int
    source_file_name_buffer_size: int


@dataclass(frozen=True)
class AssetEntryData:
    type_id: int
    instance_id: int
    type_hash: int
    instance_hash: int
    asset_reference_offset: int
    asset_reference_count: int
    name_offset: int
    source_file_name_offset: int
    instance_data_size: int
    relocation_data_size: int
    imports_data_size: int
    tokenized: int

    @property
    def key(self) -> tuple[int, int]:
        return self.type_id, self.instance_id

    @property
    def has_linked_data(self) -> bool:
        return bool(
            self.instance_data_size
            or self.relocation_data_size
            or self.imports_data_size
        )


@dataclass(frozen=True)
class ManifestData:
    raw: bytes
    header: ManifestHeaderData
    entries: tuple[AssetEntryData, ...]
    reference_manifests: tuple[tuple[int, str], ...]
    asset_entries_offset: int
    asset_reference_buffer_offset: int
    reference_manifest_buffer_offset: int
    asset_name_buffer_offset: int
    source_file_name_buffer_offset: int

    @classmethod
    def parse(cls, raw: bytes) -> "ManifestData":
        if len(raw) < MANIFEST_HEADER.size:
            raise ValueError("Truncated linked-stream manifest header")
        version = struct.unpack_from("<H", raw, 2)[0]
        if version == 6:
            values = MANIFEST_HEADER.unpack_from(raw)
            header = ManifestHeaderData(*values)
            entries_offset = MANIFEST_HEADER.size
        elif len(raw) >= MANIFEST_HEADER_V7.size and struct.unpack_from(
            "<H", raw, 4
        )[0] == 7:
            (
                _reserved,
                version,
                big_endian,
                linked,
                *values,
            ) = MANIFEST_HEADER_V7.unpack_from(raw)
            header = ManifestHeaderData(big_endian, linked, version, *values)
            entries_offset = MANIFEST_HEADER_V7.size
        else:
            raise ValueError(f"Unsupported manifest version: {version}")
        if header.big_endian:
            raise ValueError("Big-endian manifests are not supported")
        if header.version not in (6, 7):
            raise ValueError(f"Unsupported manifest version: {header.version}")

        references_offset = entries_offset + header.asset_count * ASSET_ENTRY.size
        manifest_names_offset = references_offset + header.asset_reference_buffer_size
        asset_names_offset = (
            manifest_names_offset + header.reference_manifest_name_buffer_size
        )
        source_names_offset = asset_names_offset + header.asset_name_buffer_size
        expected_size = source_names_offset + header.source_file_name_buffer_size
        if expected_size != len(raw):
            raise ValueError(
                f"Manifest size mismatch: expected {expected_size}, got {len(raw)}"
            )

        entries: list[AssetEntryData] = []
        for index in range(header.asset_count):
            offset = entries_offset + index * ASSET_ENTRY.size
            entry = AssetEntryData(*ASSET_ENTRY.unpack_from(raw, offset))
            reference_end = (
                entry.asset_reference_offset + entry.asset_reference_count * 8
            )
            if reference_end > header.asset_reference_buffer_size:
                raise ValueError(f"Asset {index} has invalid reference bounds")
            if entry.name_offset >= max(1, header.asset_name_buffer_size):
                raise ValueError(f"Asset {index} has an invalid name offset")
            if entry.source_file_name_offset >= max(
                1, header.source_file_name_buffer_size
            ):
                raise ValueError(f"Asset {index} has an invalid source-name offset")
            entries.append(entry)

        reference_manifests: list[tuple[int, str]] = []
        cursor = manifest_names_offset
        while cursor < asset_names_offset:
            reference_type = raw[cursor]
            cursor += 1
            end = raw.find(b"\0", cursor, asset_names_offset)
            if end < 0:
                raise ValueError("Unterminated referenced-manifest name")
            reference_manifests.append(
                (reference_type, raw[cursor:end].decode("latin-1"))
            )
            cursor = end + 1
        if cursor != asset_names_offset:
            raise ValueError("Referenced-manifest buffer is misaligned")

        return cls(
            raw=raw,
            header=header,
            entries=tuple(entries),
            reference_manifests=tuple(reference_manifests),
            asset_entries_offset=entries_offset,
            asset_reference_buffer_offset=references_offset,
            reference_manifest_buffer_offset=manifest_names_offset,
            asset_name_buffer_offset=asset_names_offset,
            source_file_name_buffer_offset=source_names_offset,
        )


def convert_manifest_version(
    raw: bytes, version: int, *, all_types_hash: int | None = None
) -> bytes:
    """Rewrap an unchanged PC manifest as version 6 or 7.

    Versions 6 and 7 use the same asset entries and buffers and have equal-size
    headers; Uprising merely rearranges the four leading control fields.  This
    bridge lets the RA3 BinaryAssetBuilder read Uprising reference manifests
    while compiling against the Uprising schemas.  It does not convert linked
    stream payload files.
    """

    if version not in (6, 7):
        raise ValueError(f"Unsupported target manifest version: {version}")
    manifest = ManifestData.parse(raw)
    header = manifest.header
    if all_types_hash is None:
        all_types_hash = header.all_types_hash
    if not 0 <= all_types_hash <= 0xFFFFFFFF:
        raise ValueError("all_types_hash must be an unsigned 32-bit value")
    fields = (
        header.stream_checksum,
        all_types_hash,
        header.asset_count,
        header.total_instance_data_size,
        header.max_instance_chunk_size,
        header.max_relocation_chunk_size,
        header.max_imports_chunk_size,
        header.asset_reference_buffer_size,
        header.reference_manifest_name_buffer_size,
        header.asset_name_buffer_size,
        header.source_file_name_buffer_size,
    )
    if version == 6:
        converted_header = MANIFEST_HEADER.pack(
            header.big_endian, header.linked, version, *fields
        )
    else:
        converted_header = MANIFEST_HEADER_V7.pack(
            0, version, header.big_endian, header.linked, *fields
        )
    return converted_header + raw[manifest.asset_entries_offset :]


@dataclass(frozen=True)
class LinkedAssetData:
    """One asset and its complete linked-stream payload."""

    entry: AssetEntryData
    asset_references: bytes
    name: str
    source_file_name: str
    instance_data: bytes
    imports_data: bytes
    relocation_data: bytes


@dataclass(frozen=True)
class LinkedStreamData:
    manifest: bytes
    binary: bytes
    imports: bytes
    relocations: bytes


def _manifest_string(raw: bytes, start: int, size: int, offset: int) -> str:
    if offset >= size:
        raise ValueError("Manifest string offset is outside its buffer")
    end = raw.find(b"\0", start + offset, start + size)
    if end < 0:
        raise ValueError("Unterminated manifest string")
    return raw[start + offset : end].decode("latin-1")


def extract_linked_assets(
    manifest_raw: bytes,
    binary_raw: bytes,
    imports_raw: bytes,
    relocations_raw: bytes,
) -> tuple[LinkedAssetData, ...]:
    """Extract all assets from a self-contained retail linked stream."""

    validate_linked_stream(manifest_raw, binary_raw, imports_raw, relocations_raw)
    manifest = ManifestData.parse(manifest_raw)
    stream_header_size = 8 if manifest.header.version == 7 else 4
    binary_offset = stream_header_size
    imports_offset = stream_header_size
    relocations_offset = stream_header_size
    assets: list[LinkedAssetData] = []
    for entry in manifest.entries:
        binary_end = binary_offset + entry.instance_data_size
        imports_end = imports_offset + entry.imports_data_size
        relocations_end = relocations_offset + entry.relocation_data_size
        reference_start = (
            manifest.asset_reference_buffer_offset + entry.asset_reference_offset
        )
        reference_end = reference_start + entry.asset_reference_count * 8
        assets.append(
            LinkedAssetData(
                entry=entry,
                asset_references=manifest.raw[reference_start:reference_end],
                name=_manifest_string(
                    manifest.raw,
                    manifest.asset_name_buffer_offset,
                    manifest.header.asset_name_buffer_size,
                    entry.name_offset,
                ),
                source_file_name=_manifest_string(
                    manifest.raw,
                    manifest.source_file_name_buffer_offset,
                    manifest.header.source_file_name_buffer_size,
                    entry.source_file_name_offset,
                ),
                instance_data=binary_raw[binary_offset:binary_end],
                imports_data=imports_raw[imports_offset:imports_end],
                relocation_data=relocations_raw[
                    relocations_offset:relocations_end
                ],
            )
        )
        binary_offset = binary_end
        imports_offset = imports_end
        relocations_offset = relocations_end
    return tuple(assets)


def extract_linked_patch_assets(
    manifest_raw: bytes,
    binary_raw: bytes,
    imports_raw: bytes,
    relocations_raw: bytes,
    previous_manifest_raw: bytes,
) -> tuple[LinkedAssetData, ...]:
    """Extract only the payloads carried by one retail patch manifest.

    RA3 retail patch manifests repeat the complete effective asset catalog,
    including inherited chunk sizes, while their three linked data files hold
    only new or changed instances.  An instance is carried by the patch when
    its ID is new or its instance hash differs from the preceding manifest.
    Type-hash-only schema transitions do not carry another payload.
    """

    manifest = ManifestData.parse(manifest_raw)
    previous = ManifestData.parse(previous_manifest_raw)
    if not manifest.header.linked:
        raise ValueError("Patch manifest must describe a linked stream")
    if manifest.header.version != previous.header.version:
        raise ValueError("Patch-chain manifest versions differ")

    previous_by_key = {entry.key: entry for entry in previous.entries}
    if len(previous_by_key) != len(previous.entries):
        raise ValueError("Previous manifest contains duplicate asset IDs")
    current_by_key = {entry.key: entry for entry in manifest.entries}
    if len(current_by_key) != len(manifest.entries):
        raise ValueError("Patch manifest contains duplicate asset IDs")
    linked_entries = tuple(
        entry
        for entry in manifest.entries
        if entry.key not in previous_by_key
        or entry.instance_hash != previous_by_key[entry.key].instance_hash
    )

    stream_header_size = 8 if manifest.header.version == 7 else 4
    checksum_offset = 4 if manifest.header.version == 7 else 0
    expected = {
        "binary": stream_header_size
        + sum(entry.instance_data_size for entry in linked_entries),
        "imports": stream_header_size
        + sum(entry.imports_data_size for entry in linked_entries),
        "relocations": stream_header_size
        + sum(entry.relocation_data_size for entry in linked_entries),
    }
    streams = {
        "binary": binary_raw,
        "imports": imports_raw,
        "relocations": relocations_raw,
    }
    actual = {label: len(raw) for label, raw in streams.items()}
    if actual != expected:
        raise ValueError(f"Linked patch length mismatch: {actual} != {expected}")

    checksum = struct.pack("<I", manifest.header.stream_checksum)
    for label, raw in streams.items():
        if manifest.header.version == 7 and raw[:4] != STREAM_MAGIC_V7[label]:
            raise ValueError(f"{label} patch stream has invalid version-7 magic")
        if raw[checksum_offset : checksum_offset + 4] != checksum:
            raise ValueError(
                f"{label} patch stream checksum does not match the manifest"
            )

    binary_offset = stream_header_size
    imports_offset = stream_header_size
    relocations_offset = stream_header_size
    assets: list[LinkedAssetData] = []
    for entry in linked_entries:
        binary_end = binary_offset + entry.instance_data_size
        imports_end = imports_offset + entry.imports_data_size
        relocations_end = relocations_offset + entry.relocation_data_size
        reference_start = (
            manifest.asset_reference_buffer_offset + entry.asset_reference_offset
        )
        reference_end = reference_start + entry.asset_reference_count * 8
        assets.append(
            LinkedAssetData(
                entry=entry,
                asset_references=manifest.raw[reference_start:reference_end],
                name=_manifest_string(
                    manifest.raw,
                    manifest.asset_name_buffer_offset,
                    manifest.header.asset_name_buffer_size,
                    entry.name_offset,
                ),
                source_file_name=_manifest_string(
                    manifest.raw,
                    manifest.source_file_name_buffer_offset,
                    manifest.header.source_file_name_buffer_size,
                    entry.source_file_name_offset,
                ),
                instance_data=binary_raw[binary_offset:binary_end],
                imports_data=imports_raw[imports_offset:imports_end],
                relocation_data=relocations_raw[
                    relocations_offset:relocations_end
                ],
            )
        )
        binary_offset = binary_end
        imports_offset = imports_end
        relocations_offset = relocations_end
    return tuple(assets)


def reconstruct_linked_patch_chain(
    base: LinkedStreamData,
    patches: Sequence[LinkedStreamData],
) -> LinkedStreamData:
    """Materialize a retail base plus incremental patches as one stream."""

    effective = list(
        extract_linked_assets(
            base.manifest,
            base.binary,
            base.imports,
            base.relocations,
        )
    )
    previous_manifest = ManifestData.parse(base.manifest)

    for patch in patches:
        current_manifest = ManifestData.parse(patch.manifest)
        changed = extract_linked_patch_assets(
            patch.manifest,
            patch.binary,
            patch.imports,
            patch.relocations,
            previous_manifest.raw,
        )
        changed_by_key = {asset.entry.key: asset for asset in changed}
        if len(changed_by_key) != len(changed):
            raise ValueError("Patch payload contains duplicate asset IDs")
        effective_by_key = {asset.entry.key: asset for asset in effective}
        if len(effective_by_key) != len(effective):
            raise ValueError("Effective stream contains duplicate asset IDs")

        next_effective: list[LinkedAssetData] = []
        for entry in current_manifest.entries:
            asset = changed_by_key.get(entry.key)
            carried_by_patch = asset is not None
            if asset is None:
                asset = effective_by_key.get(entry.key)
                if asset is None:
                    raise ValueError(
                        "Patch inherits an unavailable asset: "
                        f"{entry.type_id:08x}:{entry.instance_id:08x}"
                    )
                if asset.entry.instance_hash != entry.instance_hash:
                    raise ValueError(
                        "Patch omitted a changed asset payload: "
                        f"{entry.type_id:08x}:{entry.instance_id:08x}"
                    )

            if carried_by_patch:
                sizes = (
                    len(asset.instance_data),
                    len(asset.relocation_data),
                    len(asset.imports_data),
                )
                expected_sizes = (
                    entry.instance_data_size,
                    entry.relocation_data_size,
                    entry.imports_data_size,
                )
                if sizes != expected_sizes:
                    raise ValueError(
                        "Effective payload size differs from the patch manifest "
                        f"for {entry.type_id:08x}:{entry.instance_id:08x}: "
                        f"{sizes} != {expected_sizes}"
                    )
            elif entry.has_linked_data:
                raise ValueError(
                    "Patch has unaccounted linked data for unchanged asset: "
                    f"{entry.type_id:08x}:{entry.instance_id:08x}"
                )

            reference_start = (
                current_manifest.asset_reference_buffer_offset
                + entry.asset_reference_offset
            )
            reference_end = reference_start + entry.asset_reference_count * 8
            next_effective.append(
                LinkedAssetData(
                    entry=entry,
                    asset_references=current_manifest.raw[
                        reference_start:reference_end
                    ],
                    name=_manifest_string(
                        current_manifest.raw,
                        current_manifest.asset_name_buffer_offset,
                        current_manifest.header.asset_name_buffer_size,
                        entry.name_offset,
                    ),
                    source_file_name=_manifest_string(
                        current_manifest.raw,
                        current_manifest.source_file_name_buffer_offset,
                        current_manifest.header.source_file_name_buffer_size,
                        entry.source_file_name_offset,
                    ),
                    instance_data=asset.instance_data,
                    imports_data=asset.imports_data,
                    relocation_data=asset.relocation_data,
                )
            )

        calculated_checksum = binary_asset_builder_output_checksum(
            [asset.entry for asset in next_effective]
        )
        if calculated_checksum != current_manifest.header.stream_checksum:
            raise ValueError(
                "Reconstructed patch checksum differs from its manifest: "
                f"{calculated_checksum:08x} != "
                f"{current_manifest.header.stream_checksum:08x}"
            )
        effective = next_effective
        previous_manifest = current_manifest

    external_references = tuple(
        reference
        for reference in previous_manifest.reference_manifests
        if reference[0] != 2
    )
    result = build_linked_stream(
        effective,
        version=previous_manifest.header.version,
        stream_checksum=previous_manifest.header.stream_checksum,
        all_types_hash=previous_manifest.header.all_types_hash,
        reference_manifests=external_references,
    )
    rebuilt = ManifestData.parse(result.manifest)
    expected_header_values = (
        previous_manifest.header.asset_count,
        previous_manifest.header.total_instance_data_size,
        previous_manifest.header.max_instance_chunk_size,
        previous_manifest.header.max_relocation_chunk_size,
        previous_manifest.header.max_imports_chunk_size,
    )
    actual_header_values = (
        rebuilt.header.asset_count,
        rebuilt.header.total_instance_data_size,
        rebuilt.header.max_instance_chunk_size,
        rebuilt.header.max_relocation_chunk_size,
        rebuilt.header.max_imports_chunk_size,
    )
    if actual_header_values != expected_header_values:
        raise ValueError(
            "Reconstructed stream header differs from the final retail manifest: "
            f"{actual_header_values} != {expected_header_values}"
        )
    return result


def build_linked_stream(
    assets: Sequence[LinkedAssetData],
    *,
    version: int,
    stream_checksum: int,
    all_types_hash: int,
    reference_manifests: Sequence[tuple[int, str]] = (),
) -> LinkedStreamData:
    """Build a deterministic PC linked stream from complete asset payloads."""

    if version not in (6, 7):
        raise ValueError(f"Unsupported manifest version: {version}")
    if not 0 <= stream_checksum <= 0xFFFFFFFF:
        raise ValueError("Stream checksum must be an unsigned 32-bit integer")
    if not 0 <= all_types_hash <= 0xFFFFFFFF:
        raise ValueError("All-types hash must be an unsigned 32-bit integer")

    packed_entries = bytearray()
    asset_reference_buffer = bytearray()
    asset_name_buffer = bytearray()
    source_file_name_buffer = bytearray()
    instance_chunks: list[bytes] = []
    imports_chunks: list[bytes] = []
    relocation_chunks: list[bytes] = []
    seen_keys: set[tuple[int, int]] = set()

    for asset in assets:
        entry = asset.entry
        if entry.key in seen_keys:
            raise ValueError(
                "Duplicate linked asset ID: "
                f"{entry.type_id:08x}:{entry.instance_id:08x}"
            )
        seen_keys.add(entry.key)
        if len(asset.asset_references) % 8:
            raise ValueError("Asset-reference data must contain 8-byte IDs")
        for label, value in (
            ("asset name", asset.name),
            ("source file name", asset.source_file_name),
        ):
            if not value or "\0" in value:
                raise ValueError(f"Invalid {label}")
        try:
            encoded_name = asset.name.encode("latin-1")
            encoded_source = asset.source_file_name.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError("Manifest strings must be Latin-1") from exc

        reference_offset = len(asset_reference_buffer)
        name_offset = len(asset_name_buffer)
        source_offset = len(source_file_name_buffer)
        asset_reference_buffer.extend(asset.asset_references)
        asset_name_buffer.extend(encoded_name + b"\0")
        source_file_name_buffer.extend(encoded_source + b"\0")
        instance_data = bytes(asset.instance_data)
        imports_data = bytes(asset.imports_data)
        relocation_data = bytes(asset.relocation_data)
        instance_chunks.append(instance_data)
        imports_chunks.append(imports_data)
        relocation_chunks.append(relocation_data)
        packed_entries.extend(
            ASSET_ENTRY.pack(
                entry.type_id,
                entry.instance_id,
                entry.type_hash,
                entry.instance_hash,
                reference_offset,
                len(asset.asset_references) // 8,
                name_offset,
                source_offset,
                len(instance_data),
                len(relocation_data),
                len(imports_data),
                entry.tokenized,
            )
        )

    reference_manifest_buffer = bytearray()
    for reference_type, name in reference_manifests:
        if not 0 <= reference_type <= 0xFF or not name or "\0" in name:
            raise ValueError("Invalid referenced-manifest entry")
        try:
            encoded_name = name.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError("Referenced-manifest names must be Latin-1") from exc
        reference_manifest_buffer.append(reference_type)
        reference_manifest_buffer.extend(encoded_name + b"\0")

    instance_sizes = [len(chunk) for chunk in instance_chunks]
    relocation_sizes = [len(chunk) for chunk in relocation_chunks]
    imports_sizes = [len(chunk) for chunk in imports_chunks]
    fields = (
        stream_checksum,
        all_types_hash,
        len(assets),
        sum(instance_sizes),
        max(instance_sizes, default=0),
        max(relocation_sizes, default=0),
        max(imports_sizes, default=0),
        len(asset_reference_buffer),
        len(reference_manifest_buffer),
        len(asset_name_buffer),
        len(source_file_name_buffer),
    )
    if version == 6:
        header = MANIFEST_HEADER.pack(0, 1, version, *fields)
    else:
        header = MANIFEST_HEADER_V7.pack(0, version, 0, 1, *fields)
    manifest_raw = bytes(
        header
        + packed_entries
        + asset_reference_buffer
        + reference_manifest_buffer
        + asset_name_buffer
        + source_file_name_buffer
    )
    checksum = struct.pack("<I", stream_checksum)
    if version == 7:
        binary_prefix = STREAM_MAGIC_V7["binary"] + checksum
        imports_prefix = STREAM_MAGIC_V7["imports"] + checksum
        relocations_prefix = STREAM_MAGIC_V7["relocations"] + checksum
    else:
        binary_prefix = imports_prefix = relocations_prefix = checksum
    result = LinkedStreamData(
        manifest=manifest_raw,
        binary=binary_prefix + b"".join(instance_chunks),
        imports=imports_prefix + b"".join(imports_chunks),
        relocations=relocations_prefix + b"".join(relocation_chunks),
    )
    validate_linked_stream(
        result.manifest,
        result.binary,
        result.imports,
        result.relocations,
    )
    return result


@dataclass(frozen=True)
class RebaseStats:
    inherited_assets: int
    changed_existing_assets: int
    new_assets: int


def rebase_patch_manifest(
    mod_manifest_raw: bytes,
    compile_base_manifest_raw: bytes,
    retail_manifest_raw: bytes,
    retail_manifest_name: str,
) -> tuple[bytes, RebaseStats]:
    """Rebase a BAB-linked mod stream onto an installed retail patch stream.

    BinaryAssetBuilder copies metadata (including chunk sizes) for assets
    inherited from its compile-time base manifest, while omitting their chunks
    from the linked data files.  Inherited assets are therefore identified by
    matching IDs and hashes, not by zero-sized chunks.  Retail patch chains can
    carry different hashes for those same assets, so inherited hashes are
    replaced by the installed retail manifest's values.  Compiled overrides
    retain their own hashes and linked chunks.
    """

    mod = ManifestData.parse(mod_manifest_raw)
    compile_base = ManifestData.parse(compile_base_manifest_raw)
    retail = ManifestData.parse(retail_manifest_raw)
    if not mod.header.linked or not retail.header.linked:
        raise ValueError("Mod and retail manifests must describe linked streams")
    if not (
        mod.header.all_types_hash
        == compile_base.header.all_types_hash
        == retail.header.all_types_hash
    ):
        raise ValueError("Manifest schema hashes do not match")
    if not retail_manifest_name or "\0" in retail_manifest_name:
        raise ValueError("Invalid retail manifest name")
    try:
        encoded_name = retail_manifest_name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Retail manifest name must be ASCII") from exc

    compile_by_key = {entry.key: entry for entry in compile_base.entries}
    if len(compile_by_key) != len(compile_base.entries):
        raise ValueError("Compile-time base manifest contains duplicate asset IDs")
    retail_by_key = {entry.key: entry for entry in retail.entries}
    if len(retail_by_key) != len(retail.entries):
        raise ValueError("Retail manifest contains duplicate asset IDs")

    output = bytearray(mod_manifest_raw)
    inherited = 0
    changed_existing = 0
    new = 0
    for index, entry in enumerate(mod.entries):
        compile_entry = compile_by_key.get(entry.key)
        retail_entry = retail_by_key.get(entry.key)
        is_inherited = bool(
            compile_entry
            and entry.type_hash == compile_entry.type_hash
            and entry.instance_hash == compile_entry.instance_hash
        )
        if is_inherited:
            if retail_entry is None:
                raise ValueError(
                    "An inherited mod asset is absent from the retail base: "
                    f"{entry.type_id:08x}:{entry.instance_id:08x}"
                )
            entry_offset = mod.asset_entries_offset + index * ASSET_ENTRY.size
            struct.pack_into(
                "<II",
                output,
                entry_offset + 8,
                retail_entry.type_hash,
                retail_entry.instance_hash,
            )
            inherited += 1
        elif retail_entry is None:
            new += 1
        else:
            changed_existing += 1

    rebased_references: list[tuple[int, str]] = []
    patch_reference_seen = False
    for reference_type, reference_name in mod.reference_manifests:
        if reference_type == 2:
            if patch_reference_seen:
                raise ValueError("Mod manifest contains multiple patch-base references")
            patch_reference_seen = True
            rebased_references.append((2, retail_manifest_name))
        else:
            if "\0" in reference_name:
                raise ValueError("Invalid referenced-manifest name")
            rebased_references.append((reference_type, reference_name))
    if not patch_reference_seen:
        rebased_references.insert(0, (2, retail_manifest_name))

    try:
        new_reference_buffer = b"".join(
            bytes((reference_type,)) + reference_name.encode("latin-1") + b"\0"
            for reference_type, reference_name in rebased_references
        )
    except UnicodeEncodeError as exc:
        raise ValueError("Referenced-manifest names must be Latin-1") from exc
    old_reference_start = mod.reference_manifest_buffer_offset
    old_reference_end = mod.asset_name_buffer_offset
    reference_size_offset = 36 if mod.header.version == 6 else 40
    struct.pack_into("<I", output, reference_size_offset, len(new_reference_buffer))
    output = (
        output[:old_reference_start]
        + new_reference_buffer
        + output[old_reference_end:]
    )
    parsed_output = ManifestData.parse(bytes(output))
    if parsed_output.reference_manifests != tuple(rebased_references):
        raise ValueError("Rebased manifest reference verification failed")
    return bytes(output), RebaseStats(inherited, changed_existing, new)


def validate_linked_stream(
    manifest_raw: bytes,
    binary_raw: bytes,
    imports_raw: bytes,
    relocations_raw: bytes,
    compile_base_manifest_raw: bytes | None = None,
) -> None:
    manifest = ManifestData.parse(manifest_raw)
    linked_entries: Iterable[AssetEntryData] = manifest.entries
    if compile_base_manifest_raw is not None:
        compile_base = ManifestData.parse(compile_base_manifest_raw)
        if not manifest.header.linked:
            raise ValueError("The validated manifest must describe a linked stream")
        if manifest.header.all_types_hash != compile_base.header.all_types_hash:
            raise ValueError("Manifest schema hashes do not match")
        compile_by_key = {entry.key: entry for entry in compile_base.entries}
        if len(compile_by_key) != len(compile_base.entries):
            raise ValueError("Compile-time base manifest contains duplicate asset IDs")
        linked_entries = tuple(
            entry
            for entry in manifest.entries
            if not (
                (base_entry := compile_by_key.get(entry.key))
                and entry.type_hash == base_entry.type_hash
                and entry.instance_hash == base_entry.instance_hash
            )
        )
    linked_entries = tuple(linked_entries)
    stream_header_size = 8 if manifest.header.version == 7 else 4
    checksum_offset = 4 if manifest.header.version == 7 else 0
    expected = {
        "binary": stream_header_size
        + sum(entry.instance_data_size for entry in linked_entries),
        "imports": stream_header_size
        + sum(entry.imports_data_size for entry in linked_entries),
        "relocations": stream_header_size
        + sum(entry.relocation_data_size for entry in linked_entries),
    }
    actual = {
        "binary": len(binary_raw),
        "imports": len(imports_raw),
        "relocations": len(relocations_raw),
    }
    if actual != expected:
        raise ValueError(f"Linked stream length mismatch: {actual} != {expected}")
    checksum = struct.pack("<I", manifest.header.stream_checksum)
    for label, raw in (
        ("binary", binary_raw),
        ("imports", imports_raw),
        ("relocations", relocations_raw),
    ):
        if raw[checksum_offset : checksum_offset + 4] != checksum:
            raise ValueError(f"{label} stream checksum does not match the manifest")
    if (
        compile_base_manifest_raw is None
        and manifest.header.total_instance_data_size
        != expected["binary"] - stream_header_size
    ):
        raise ValueError("Manifest total instance data size is incorrect")


def build_big(
    entries: Sequence[tuple[str, bytes | bytearray | str | os.PathLike[str]]],
    output_path: str | os.PathLike[str],
) -> Path:
    """Write a deterministic, uncompressed BIG4 archive."""

    normalized: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for archive_name, source in entries:
        name = archive_name.replace("/", "\\")
        parts = name.split("\\")
        if (
            not name
            or "\0" in name
            or name.startswith("\\")
            or ":" in parts[0]
            or any(part in ("", ".", "..") for part in parts)
        ):
            raise ValueError(f"Unsafe BIG entry name: {archive_name!r}")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"Duplicate BIG entry name: {name}")
        seen.add(key)
        if isinstance(source, (bytes, bytearray)):
            payload = bytes(source)
        else:
            payload = Path(source).read_bytes()
        normalized.append((name, payload))

    table_size = sum(BIG_ENTRY.size + len(name.encode("latin-1")) + 1 for name, _ in normalized)
    data_start = BIG_HEADER_SIZE + table_size
    offset = data_start
    table = bytearray()
    for name, payload in normalized:
        encoded = name.encode("latin-1")
        table.extend(BIG_ENTRY.pack(offset, len(payload)))
        table.extend(encoded)
        table.append(0)
        offset += len(payload)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(b"BIG4")
        stream.write(struct.pack("<I", offset))
        stream.write(struct.pack(">II", len(normalized), data_start))
        stream.write(table)
        for _, payload in normalized:
            stream.write(payload)
    os.replace(temporary, destination)
    return destination
