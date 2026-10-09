"""Build an Uprising-native ore override from local retail data, no SDK assets.

The retail static stream is retained byte for byte except the named OreNode
capacity and its identity/checksum metadata. The low/medium streams inherit
that object and receive the matching identity. Nothing else is recompiled.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import struct

from ra3_auto.sage import (BigArchive, ManifestData, ASSET_ENTRY,
    _manifest_string, derive_modified_instance_hash, build_big)

from ra3_auto.ore_disk import ROOT
OUTPUT = ROOT
STOCK = struct.pack('<III', 30000, 250, 60)
PATCHED = struct.pack('<III', 100000, 250, 60)


def ore_entry(manifest):
    found = [(i, e) for i, e in enumerate(manifest.entries)
        if _manifest_string(manifest.raw, manifest.asset_name_buffer_offset,
            manifest.header.asset_name_buffer_size, e.name_offset) == 'GameObject:OreNode']
    if len(found) != 1:
        raise ValueError(f'Expected exactly one retail OreNode; found {len(found)}')
    return found[0]


def patch_payload(payload):
    offset = payload.find(STOCK)
    if offset < 0 or payload.find(STOCK, offset + 1) >= 0:
        raise ValueError('Expected exactly one complete retail ore capacity signature')
    result = bytearray(payload)
    result[offset:offset + 4] = struct.pack('<I', 100000)
    assert result[:offset] == payload[:offset] and result[offset + 4:] == payload[offset + 4:]
    return bytes(result), offset


def build_override(game, output=OUTPUT):
    game, output = Path(game).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'Uprising-Ore100K-Retail-v2.big'
    if target.exists():
        raise FileExistsError('Preserve an existing build: ' + str(target))
    archive = BigArchive(game / 'Data' / 'StaticStream.big')
    packaged = []
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
        'game': str(game), 'ore_capacity': 100000, 'streams': []}
    new_hash = old_hash = None
    for prefix in ('static', 'static_l', 'static_m'):
        files = {ext: archive.read('data\\' + prefix + '.' + ext)
            for ext in ('manifest', 'bin', 'imp', 'relo')}
        manifest = ManifestData.parse(files['manifest'])
        if manifest.header.version != 7 or not manifest.header.linked:
            raise ValueError('Requires Uprising retail linked stream version 7')
        index, entry = ore_entry(manifest)
        if prefix == 'static':
            start = 8 + sum(e.instance_data_size for e in manifest.entries[:index])
            end = start + entry.instance_data_size
            original = files['bin'][start:end]
            if hashlib.sha256(original).hexdigest() != '380fd98b2ffcf3c2e70384755bb8f3ae5c64c328aae36bdab9c698dd8359d70a':
                raise ValueError('Unsupported retail OreNode asset; refusing to build')
            changed, offset = patch_payload(original)
            old_hash = entry.instance_hash
            new_hash = derive_modified_instance_hash(old_hash, changed, purpose='uprising-ore100k-retail-v2')
            files['bin'] = files['bin'][:start] + changed + files['bin'][end:]
            report['ore_payload_offset'] = start + offset
            report['ore_asset_offset'] = offset
            report['original_asset_sha256'] = hashlib.sha256(original).hexdigest()
        else:
            assert entry.instance_hash == old_hash
            assert not entry.has_linked_data, 'LOD OreNode must inherit the original object'
        updated = bytearray(files['manifest'])
        struct.pack_into('<I', updated, manifest.asset_entries_offset + index * ASSET_ENTRY.size + 12, new_hash)
        checksum = derive_modified_instance_hash(manifest.header.stream_checksum,
            struct.pack('<I', new_hash), purpose='uprising-ore-stream-v2-' + prefix)
        struct.pack_into('<I', updated, 8, checksum)
        files['manifest'] = bytes(updated)
        for ext in ('bin', 'imp', 'relo'):
            files[ext] = files[ext][:4] + struct.pack('<I', checksum) + files[ext][8:]
        for ext, raw in files.items():
            packaged.append(('data\\' + prefix + '.' + ext, raw))
        report['streams'].append({'name': prefix, 'ore_index': index,
            'old_instance_hash': old_hash, 'new_instance_hash': new_hash, 'checksum': checksum})
    build_big(packaged, target)
    check = BigArchive(target)
    patched_binary = check.read('data\\static.bin')
    assert patched_binary[report['ore_payload_offset']:report['ore_payload_offset'] + 12] == PATCHED
    for stream in report['streams']:
        m = ManifestData.parse(check.read('data\\' + stream['name'] + '.manifest'))
        assert ore_entry(m)[1].instance_hash == new_hash
        for ext in ('bin', 'imp', 'relo'):
            assert struct.unpack_from('<I', check.read('data\\' + stream['name'] + '.' + ext), 4)[0] == m.header.stream_checksum
    report['override'] = str(target)
    report['override_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / 'build-receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
