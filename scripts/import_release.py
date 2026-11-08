"""Import an unmodified Synth release; pin archive and extracted file hashes."""
import argparse
import hashlib
import io
import json
import posixpath
import re
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# The checked standalone release ships four native components. These exact
# rebuild-input names are independent of their versioned hashes in the receipts.
BROWSER_RECEIPT = 'sources/sid-synth-browser.json'
BROWSER_SOURCE_ARCHIVE = 'sources/sid-synth-browser-inputs.zip'
BROWSER_ENTRIES = {'synth-sid/synth.js', 'synth-sid/processor.js', 'synth-sid/synth.css', 'sid-player/processor.js'}
NATIVE_INPUTS = {'sid': {'LICENSE',
         'scripts/build_sid_wasm.sh',
         'scripts/check_sid_native.mjs',
         'scripts/prepare_sid_core.py',
         'scripts/sid_artifacts.mjs',
         'test/helpers/sid_reference.cpp',
         'tetorica_src/wasm/sid_core.h',
         'tetorica_src/wasm/sid_wasm.cpp',
         'third_party/chips-m6581/LICENSE',
         'third_party/chips-m6581/PATCHES.md',
         'third_party/chips-m6581/README.md',
         'third_party/chips-m6581/m6581.h',
         'third_party/chips-m6581/upstream/m6581.h'},
 'sid-player': {'LICENSE',
                'scripts/build_sid_player_wasm.sh',
                'scripts/prepare_sid_core.py',
                'scripts/sid_player_artifacts.mjs',
                'tetorica_src/wasm/sid_player_core.h',
                'tetorica_src/wasm/sid_player_wasm.cpp',
                'third_party/chips-m6502/LICENSE',
                'third_party/chips-m6502/README.md',
                'third_party/chips-m6502/upstream/m6502.h',
                'third_party/chips-m6581/LICENSE',
                'third_party/chips-m6581/PATCHES.md',
                'third_party/chips-m6581/README.md',
                'third_party/chips-m6581/m6581.h',
                'third_party/chips-m6581/upstream/m6581.h'},
 'sid-rsid': {'LICENSE',
              'scripts/build_sid_rsid_wasm.sh',
              'scripts/prepare_sid_core.py',
              'scripts/sid_rsid_artifacts.mjs',
              'tetorica_src/wasm/sid_rsid_chip.cpp',
              'tetorica_src/wasm/sid_rsid_core.h',
              'tetorica_src/wasm/sid_rsid_machine.c',
              'tetorica_src/wasm/sid_rsid_wasm.cpp',
              'third_party/chips-c64/LICENSE',
              'third_party/chips-c64/README.md',
              'third_party/chips-c64/SOURCES.json',
              'third_party/chips-c64/upstream/chips/chips_common.h',
              'third_party/chips-c64/upstream/chips/clk.h',
              'third_party/chips-c64/upstream/chips/kbd.h',
              'third_party/chips-c64/upstream/chips/m6522.h',
              'third_party/chips-c64/upstream/chips/m6526.h',
              'third_party/chips-c64/upstream/chips/m6569.h',
              'third_party/chips-c64/upstream/chips/mem.h',
              'third_party/chips-c64/upstream/systems/c1530.h',
              'third_party/chips-c64/upstream/systems/c1541.h',
              'third_party/chips-c64/upstream/systems/c64.h',
              'third_party/chips-m6502/LICENSE',
              'third_party/chips-m6502/README.md',
              'third_party/chips-m6502/upstream/m6502.h',
              'third_party/chips-m6581/LICENSE',
              'third_party/chips-m6581/PATCHES.md',
              'third_party/chips-m6581/README.md',
              'third_party/chips-m6581/m6581.h',
              'third_party/chips-m6581/upstream/m6581.h'},
 'sid8580-machine': {'LICENSE',
                     'scripts/build_sid8580_machine.sh',
                     'scripts/build_sid8580_probe.sh',
                     'scripts/build_sid_rsid_wasm.sh',
                     'scripts/prepare_sid8580_machine_core.mjs',
                     'scripts/prepare_sid_core.py',
                     'scripts/sid8580_machine_artifacts.mjs',
                     'scripts/sid8580_probe_artifacts.mjs',
                     'scripts/sid_rsid_artifacts.mjs',
                     'tetorica_src/wasm/sid8580-machine/endpoint.rs',
                     'tetorica_src/wasm/sid8580-machine/generated/sid8580_machine_core.h',
                     'tetorica_src/wasm/sid8580-machine/generated/source-manifest.json',
                     'tetorica_src/wasm/sid8580-machine/machine.c',
                     'tetorica_src/wasm/sid8580-machine/machine_native.cpp',
                     'tetorica_src/wasm/sid8580-machine/machine_wasm.cpp',
                     'tetorica_src/wasm/sid8580-machine/sid_endpoint.cpp',
                     'tetorica_src/wasm/sid8580-machine/sid_endpoint.h',
                     'tetorica_src/wasm/sid8580-probe/cpu.rs',
                     'tetorica_src/wasm/sid8580-probe/cpu_bridge.c',
                     'tetorica_src/wasm/sid8580-probe/cpu_native.rs',
                     'tetorica_src/wasm/sid8580-probe/lib.rs',
                     'tetorica_src/wasm/sid8580-probe/native.rs',
                     'tetorica_src/wasm/sid8580-probe/quality.rs',
                     'tetorica_src/wasm/sid8580-probe/quality_native.rs',
                     'tetorica_src/wasm/sid_rsid_chip.cpp',
                     'tetorica_src/wasm/sid_rsid_core.h',
                     'tetorica_src/wasm/sid_rsid_machine.c',
                     'tetorica_src/wasm/sid_rsid_wasm.cpp',
                     'third_party/chips-c64/LICENSE',
                     'third_party/chips-c64/README.md',
                     'third_party/chips-c64/SOURCES.json',
                     'third_party/chips-c64/upstream/chips/chips_common.h',
                     'third_party/chips-c64/upstream/chips/clk.h',
                     'third_party/chips-c64/upstream/chips/kbd.h',
                     'third_party/chips-c64/upstream/chips/m6522.h',
                     'third_party/chips-c64/upstream/chips/m6526.h',
                     'third_party/chips-c64/upstream/chips/m6569.h',
                     'third_party/chips-c64/upstream/chips/mem.h',
                     'third_party/chips-c64/upstream/systems/c1530.h',
                     'third_party/chips-c64/upstream/systems/c1541.h',
                     'third_party/chips-c64/upstream/systems/c64.h',
                     'third_party/chips-m6502/LICENSE',
                     'third_party/chips-m6502/README.md',
                     'third_party/chips-m6502/upstream/m6502.h',
                     'third_party/chips-m6581/LICENSE',
                     'third_party/chips-m6581/PATCHES.md',
                     'third_party/chips-m6581/README.md',
                     'third_party/chips-m6581/m6581.h',
                     'third_party/chips-m6581/upstream/m6581.h',
                     'third_party/sidera/8580-cutoff-calibration.json',
                     'third_party/sidera/8580-resonance-calibration.json',
                     'third_party/sidera/LICENSE',
                     'third_party/sidera/PATCHES.json',
                     'third_party/sidera/README.md',
                     'third_party/sidera/SOURCES.json',
                     'third_party/sidera/adapted/src/bin/sidplay/bus.rs',
                     'third_party/sidera/adapted/src/bin/sidplay/diag.rs',
                     'third_party/sidera/adapted/src/bin/sidplay/main.rs',
                     'third_party/sidera/adapted/src/bin/sidplay/output.rs',
                     'third_party/sidera/adapted/src/bin/sidplay/player.rs',
                     'third_party/sidera/adapted/src/bin/sidplay/psid.rs',
                     'third_party/sidera/adapted/src/envelope.rs',
                     'third_party/sidera/adapted/src/extfilt.rs',
                     'third_party/sidera/adapted/src/filter.rs',
                     'third_party/sidera/adapted/src/high.rs',
                     'third_party/sidera/adapted/src/lib.rs',
                     'third_party/sidera/adapted/src/noise.rs',
                     'third_party/sidera/adapted/src/oscillator.rs',
                     'third_party/sidera/adapted/src/registers.rs',
                     'third_party/sidera/adapted/src/sid.rs',
                     'third_party/sidera/adapted/src/voice.rs',
                     'third_party/sidera/upstream/.cargo_vcs_info.json',
                     'third_party/sidera/upstream/.gitignore',
                     'third_party/sidera/upstream/Cargo.lock',
                     'third_party/sidera/upstream/Cargo.toml',
                     'third_party/sidera/upstream/Cargo.toml.orig',
                     'third_party/sidera/upstream/LICENSE',
                     'third_party/sidera/upstream/README.md',
                     'third_party/sidera/upstream/SID_ANALOG_SPEC.md',
                     'third_party/sidera/upstream/examples/bench.rs',
                     'third_party/sidera/upstream/examples/render.rs',
                     'third_party/sidera/upstream/src/bin/sidplay/bus.rs',
                     'third_party/sidera/upstream/src/bin/sidplay/diag.rs',
                     'third_party/sidera/upstream/src/bin/sidplay/main.rs',
                     'third_party/sidera/upstream/src/bin/sidplay/output.rs',
                     'third_party/sidera/upstream/src/bin/sidplay/player.rs',
                     'third_party/sidera/upstream/src/bin/sidplay/psid.rs',
                     'third_party/sidera/upstream/src/envelope.rs',
                     'third_party/sidera/upstream/src/extfilt.rs',
                     'third_party/sidera/upstream/src/filter.rs',
                     'third_party/sidera/upstream/src/high.rs',
                     'third_party/sidera/upstream/src/lib.rs',
                     'third_party/sidera/upstream/src/noise.rs',
                     'third_party/sidera/upstream/src/oscillator.rs',
                     'third_party/sidera/upstream/src/registers.rs',
                     'third_party/sidera/upstream/src/sid.rs',
                     'third_party/sidera/upstream/src/voice.rs',
                     'third_party/sidera/upstream/tests/golden.rs',
                     'third_party/sidera/upstream/tests/integration.rs'}}
REQUIRED_NOTICES = {'third_party/chips-c64/LICENSE',
 'third_party/chips-c64/README.md',
 'third_party/chips-c64/SOURCES.json',
 'third_party/chips-m6502/LICENSE',
 'third_party/chips-m6502/README.md',
 'third_party/chips-m6581/LICENSE',
 'third_party/chips-m6581/PATCHES.md',
 'third_party/chips-m6581/README.md',
 'third_party/sid8580-machine-toolchain-notices/README.md',
 'third_party/sid8580-machine-toolchain-notices/SOURCES.json',
 'third_party/sid8580-machine-toolchain-notices/compiler-rt-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/emscripten-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/libcxx-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/libcxxabi-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/libunwind-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/llvm-libc-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/mimalloc-LICENSE.txt',
 'third_party/sid8580-machine-toolchain-notices/musl-COPYRIGHT.txt',
 'third_party/sidera/LICENSE',
 'third_party/sidera/PATCHES.json',
 'third_party/sidera/README.md',
 'third_party/sidera/SOURCES.json',
 'third_party/sidera/toolchain-notices/COPYRIGHT-library.html',
 'third_party/sidera/toolchain-notices/README.md',
 'third_party/sidera/toolchain-notices/SOURCES.json',
 'third_party/sidera/toolchain-notices/licenses/Apache-2.0.txt',
 'third_party/sidera/toolchain-notices/licenses/BSD-2-Clause.txt',
 'third_party/sidera/toolchain-notices/licenses/CC-BY-SA-4.0.txt',
 'third_party/sidera/toolchain-notices/licenses/GCC-exception-3.1.txt',
 'third_party/sidera/toolchain-notices/licenses/GPL-2.0-only.txt',
 'third_party/sidera/toolchain-notices/licenses/GPL-3.0-or-later.txt',
 'third_party/sidera/toolchain-notices/licenses/ISC.txt',
 'third_party/sidera/toolchain-notices/licenses/LLVM-exception.txt',
 'third_party/sidera/toolchain-notices/licenses/MIT.txt',
 'third_party/sidera/toolchain-notices/licenses/NCSA.txt',
 'third_party/sidera/toolchain-notices/licenses/OFL-1.1.txt',
 'third_party/sidera/toolchain-notices/licenses/Unicode-3.0.txt',
 'third_party/sidera/upstream/LICENSE',
 'third_party/sidera/upstream/README.md'}
REQUIRED = {'LICENSE',
 'generated/sid-player/sid-player-build.json',
 'generated/sid-player/sid-player.wasm',
 'generated/sid-rsid/sid-rsid-build.json',
 'generated/sid-rsid/sid-rsid.wasm',
 'generated/sid/sid-build.json',
 'generated/sid/sid.wasm',
 'generated/sid8580-machine/sid8580-endpoint.wasm',
 'generated/sid8580-machine/sid8580-machine-build.json',
 'generated/sid8580-machine/sid8580-machine.wasm',
 'index.html',
 'licenses/chips-m6581/LICENSE',
 'licenses/chips-m6581/PATCHES.md',
 'licenses/chips-m6581/README.md',
 'sources/SID-SONG-PREVIEW.md',
 'sources/SID.md',
 'sources/SID8580.md',
 'sources/sid-player/README.md',
 'sources/sid-rsid/README.md',
 'sources/sid-synth-browser-inputs.zip',
 'sources/sid-synth-browser.json',
 'sources/sid/README.md',
 'sources/sid8580-machine/README.md',
 'sources/sid8580-machine/sid8580-machine-build.json',
 'sources/sid8580-machine/source-kit.json',
 'synth-sid/index.html',
 'synth-sid/processor.js',
 'synth-sid/synth.css',
 'synth-sid/synth.js',
 'tetorica_sid_synth.webp'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_release(destination, hashes):
    missing = REQUIRED - hashes.keys()
    if missing:
        raise ValueError('Expected SID Synth ZIP; missing: ' + ', '.join(sorted(missing)))

    def record_ok(record):
        return (isinstance(record, dict) and type(record.get('bytes')) is int
                and record['bytes'] >= 0 and valid_hash(record.get('sha256')))

    def same_record(left, right):
        return (record_ok(left) and record_ok(right)
                and all(left[key] == right[key] for key in ('bytes', 'sha256')))

    def verify(record, name):
        if not record_ok(record):
            raise ValueError('Expected a valid source receipt record')
        safe_name(name)
        if name not in hashes:
            raise ValueError(f'Missing recorded release file: {name}')
        data = (destination / name).read_bytes()
        if record['bytes'] != len(data) or record['sha256'] != hashes[name]:
            raise ValueError(f'Release source receipt mismatch: {name}')

    def records(value, label):
        if not isinstance(value, list) or not value:
            raise ValueError(f'Expected {label} source records')
        result = {}
        for record in value:
            if not record_ok(record):
                raise ValueError(f'Expected a valid {label} source record')
            name = safe_name(record.get('path'))
            if name in result:
                raise ValueError(f'Duplicate {label} source record: {name}')
            result[name] = record
        return result

    def mapping(value, label):
        if not isinstance(value, dict) or not value:
            raise ValueError(f'Expected {label} source records')
        for name, record in value.items():
            safe_name(name)
            if not record_ok(record):
                raise ValueError(f'Expected a valid {label} source record: {name}')
        return value

    def read_json(name):
        return json.loads((destination / name).read_text(encoding='utf-8'), object_pairs_hook=unique_object)

    # A release is application code and its rebuild sources, never user songs,
    # ROMs, recorded audio or extra archives with uninspected payloads.
    def no_payload(name):
        if PurePosixPath(name).suffix.lower() in {
                '.sid', '.psid', '.rsid', '.mus', '.str', '.prg', '.rom', '.bin',
                '.d64', '.d71', '.d81', '.crt', '.tap', '.t64', '.p00',
                '.wav', '.aif', '.aiff', '.mp3', '.m4a', '.ogg', '.flac',
                '.spc', '.vgm', '.vgz', '.7z', '.tar', '.gz'}:
            raise ValueError(f'User firmware, song or audio payload is not a release source: {name}')
        if name.lower().endswith('.zip') and name != BROWSER_SOURCE_ARCHIVE:
            raise ValueError(f'Unexpected nested archive in release sources: {name}')

    for name in hashes:
        no_payload(name)
    browser = read_json(BROWSER_RECEIPT)
    if (not isinstance(browser, dict) or type(browser.get('schemaVersion')) is not int
            or browser['schemaVersion'] != 1 or browser.get('productId') != 'tetorica-sid-synth'):
        raise ValueError('Expected SID Synth source receipt')
    builder = browser.get('builder')
    if (not isinstance(builder, dict) or builder.get('name') != 'source-copy'
            or builder.get('minify') is not False or builder.get('bundle') is not False):
        raise ValueError('Expected readable source-copy browser modules without minification or bundling')
    entries = records(browser.get('bundles'), 'browser entry')
    if entries.keys() != BROWSER_ENTRIES:
        raise ValueError('Expected complete SID Synth entry receipts')
    modules = records(browser.get('modules'), 'readable browser module')
    if not BROWSER_ENTRIES <= modules.keys():
        raise ValueError('Expected all browser entries in the readable module receipts')
    original = records(browser.get('originalInputs'), 'original browser input')
    for name, record in modules.items():
        verify(record, name)
        source = original.get(safe_name(record.get('sourcePath')))
        if not same_record(record, source):
            raise ValueError(f'Browser module differs from its original source receipt: {name}')
        imports = record.get('localImports', [])
        if not isinstance(imports, list):
            raise ValueError(f'Expected local module imports: {name}')
        for dependency in imports:
            if not isinstance(dependency, str) or not dependency.startswith(('./', '../')):
                raise ValueError(f'Expected a relative local module import: {name}')
            target = safe_name(posixpath.normpath(posixpath.join(posixpath.dirname(name), re.split(r'[?#]', dependency, maxsplit=1)[0])))
            if target not in modules:
                raise ValueError(f'Missing recorded browser module dependency: {name} -> {target}')
    for name, record in entries.items():
        verify(record, name)
        if not same_record(record, modules[name]):
            raise ValueError(f'Browser entry differs from its module receipt: {name}')
    source = browser.get('sourceArchive', {})
    if not isinstance(source, dict) or source.get('path') != BROWSER_SOURCE_ARCHIVE:
        raise ValueError('Expected browser source archive receipt')
    verify(source, source['path'])
    # Keep the enclosed archive byte-for-byte, while authenticating every
    # original input, including all native source and build-receipt records.
    with zipfile.ZipFile(io.BytesIO((destination / source['path']).read_bytes())) as archive:
        archived = {}
        for entry in archive.infolist():
            name = safe_name(entry.filename.rstrip('/') if entry.is_dir() else entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('Unsafe browser source archive entry')
            if entry.is_dir():
                continue
            no_payload(name)
            if name in archived:
                raise ValueError('Duplicate browser source archive entry')
            archived[name] = archive.read(entry)
        if archived.keys() != original.keys():
            raise ValueError('Browser source archive differs from its original input list')
        for name, record in original.items():
            if len(archived[name]) != record['bytes'] or digest(archived[name]) != record['sha256']:
                raise ValueError(f'Browser source archive mismatch: {name}')

    def original_copy(name, source_name):
        source_name = safe_name(source_name)
        if source_name not in original:
            raise ValueError(f'Missing original source receipt: {source_name}')
        verify(original[source_name], name)

    # A module file outside the recorded graph cannot be smuggled alongside
    # it. The optional 8580 declaration is a canonical readable source copy.
    for name in hashes:
        if not name.startswith(('sources/', 'licenses/')) and name.endswith(('.js', '.mjs', '.css', '.d.ts')) and name not in modules:
            if name != 'js/sid8580.d.ts':
                raise ValueError(f'Unrecorded browser module: {name}')
            original_copy(name, 'tetorica_src/runtime/sid8580.d.ts')
    for name in ('LICENSE', 'tetorica_sid_synth.webp'):
        original_copy(name, name if name == 'LICENSE' else 'docs/' + name)

    receipts = {}
    for component, expected_inputs in NATIVE_INPUTS.items():
        receipt_name = f'generated/{component}/{component}-build.json'
        original_copy(receipt_name, 'docs/' + receipt_name)
        native = read_json(receipt_name)
        if not isinstance(native, dict) or native.get('fixedSdkArtifact') is not False:
            raise ValueError(f'Expected standalone SID native receipt: {component}')
        if component == 'sid8580-machine':
            if native.get('format') != 'tetorica-sid8580-research-machine-build' or native.get('version') != 1:
                raise ValueError('Expected SID 8580 machine build receipt')
        elif native.get('component') != ('sid-lab' if component == 'sid' else component) or native.get('schemaVersion') != 1:
            raise ValueError(f'Expected SID native component receipt: {component}')
        inputs = mapping(native.get('inputs'), component + ' native input')
        if inputs.keys() != expected_inputs:
            raise ValueError(f'Expected exact {component} core, wrapper and build recipe source inputs')
        for name, record in inputs.items():
            verify(record, f'sources/{component}/{name}')
            if not same_record(record, original.get(name)):
                raise ValueError(f'Native input differs from original source receipt: {component}: {name}')
        outputs = mapping(native.get('outputs'), component + ' output') if component == 'sid8580-machine' else {component + '.wasm': native.get('output')}
        wasm_names = {'sid8580-endpoint.wasm', 'sid8580-machine.wasm'} if component == 'sid8580-machine' else {component + '.wasm'}
        if not wasm_names <= outputs.keys():
            raise ValueError(f'Expected all {component} WASM outputs')
        for name in wasm_names:
            output_name = f'generated/{component}/{name}'
            verify(outputs[name], output_name)
            if (destination / output_name).read_bytes()[:8] != b'\0asm\1\0\0\0':
                raise ValueError(f'Invalid WASM header: {output_name}')
        if component != 'sid8580-machine':
            original_copy(f'sources/{component}/README.md', f'docs/sources/{component}/README.md')
        receipts[component] = native

    preview = records(browser.get('previewArtifacts'), '8580 preview artifact')
    expected_preview = {'generated/sid8580-machine/sid8580-endpoint.wasm', 'generated/sid8580-machine/sid8580-machine.wasm'}
    if preview.keys() != expected_preview:
        raise ValueError('Expected both 8580 preview WASMs')
    for name, record in preview.items():
        verify(record, name)
    song_kits = browser.get('songPreviewNativeKits')
    if not isinstance(song_kits, list) or len(song_kits) != 2:
        raise ValueError('Expected both song preview native kits')
    seen = set()
    for kit in song_kits:
        if not isinstance(kit, dict):
            raise ValueError('Invalid song preview native kit')
        component = kit.get('component')
        if component not in ('sid-player', 'sid-rsid') or component in seen:
            raise ValueError('Expected distinct SID song preview components')
        seen.add(component)
        if kit.get('compiledInputCount') != len(NATIVE_INPUTS[component]) or kit.get('sourceRoot') != f'sources/{component}':
            raise ValueError('Invalid song preview native source count/root')
        for key, name in (('artifact', f'generated/{component}/{component}.wasm'), ('buildReceipt', f'generated/{component}/{component}-build.json')):
            record = kit.get(key)
            if not isinstance(record, dict) or record.get('path') != name:
                raise ValueError('Invalid song preview artifact/receipt path')
            verify(record, name)

    kit_root = 'sources/sid8580-machine'
    kit = read_json(kit_root + '/source-kit.json')
    if (not isinstance(kit, dict) or kit.get('format') != 'tetorica-sid-player-8580-source-kit'
            or kit.get('version') != 1 or kit.get('compiledInputCount') != 99
            or kit.get('compilerInvocationPerformed') is not False):
        raise ValueError('Expected complete readable SID 8580 source kit')
    if mapping(kit.get('compiledInputs'), '8580 compiled input') != receipts['sid8580-machine']['inputs']:
        raise ValueError('8580 source kit compiled inputs differ from the build receipt')
    sources = mapping(kit.get('sources'), '8580 readable source')
    if not NATIVE_INPUTS['sid8580-machine'] | REQUIRED_NOTICES <= sources.keys():
        raise ValueError('Expected complete 8580 sources, licenses and toolchain notices')
    for name, record in sources.items():
        verify(record, kit_root + '/' + name)
        if not same_record(record, original.get(name)):
            raise ValueError(f'8580 source differs from original receipt: {name}')
    kit_receipt = kit.get('buildReceipt')
    if not isinstance(kit_receipt, dict) or kit_receipt.get('path') != 'sid8580-machine-build.json':
        raise ValueError('Expected 8580 source-kit build receipt')
    verify(kit_receipt, kit_root + '/sid8580-machine-build.json')
    if (destination / (kit_root + '/sid8580-machine-build.json')).read_bytes() != (destination / 'generated/sid8580-machine/sid8580-machine-build.json').read_bytes():
        raise ValueError('8580 source-kit build receipt differs from generated receipt')
    kit_preview = browser.get('previewSourceKit')
    if (not isinstance(kit_preview, dict) or kit_preview.get('path') != kit_root
            or kit_preview.get('manifest') != 'source-kit.json'
            or kit_preview.get('compiledInputCount') != 99 or kit_preview.get('buildReceipt') != kit_receipt):
        # Browser receipt paths include the source root; both carry the same
        # relative build-receipt name and byte record.
        raise ValueError('8580 browser source-kit receipt differs')
    if kit.get('artifacts') != browser.get('previewArtifacts'):
        raise ValueError('8580 source-kit artifact receipts differ')
    notice_roots = ['third_party/sidera/toolchain-notices', 'third_party/sid8580-machine-toolchain-notices']
    if kit.get('noticeRoots') != notice_roots or kit_preview.get('noticeRoots') != notice_roots:
        raise ValueError('Expected 8580 toolchain notice roots')
    for name in ('LICENSE', 'README.md', 'PATCHES.md'):
        notice = f'licenses/chips-m6581/{name}'
        original_copy(notice, f'third_party/chips-m6581/{name}')
        if (destination / notice).read_bytes() != (destination / f'sources/sid/third_party/chips-m6581/{name}').read_bytes():
            raise ValueError(f'SID license notice differs from native source copy: {name}')


def unpack(archive, destination):
    hashes = {}
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        for entry in entries:
            safe_name(entry.filename.rstrip('/') if entry.is_dir() else entry.filename)
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f'Unsafe ZIP entry: {entry.filename}')
        for entry in entries:
            if entry.is_dir():
                continue
            name = str(PurePosixPath(entry.filename))
            if name in hashes:
                raise ValueError(f'Duplicate ZIP entry: {name}')
            data = source.read(entry)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[name] = digest(data)
    validate_release(destination, hashes)
    return hashes


LOCAL_REQUIRED = {'index.html', 'synth-sid/synth.js'}
LOCAL_MANIFEST = 'local-changes.json'


def safe_name(name):
    if not isinstance(name, str) or not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError('Expected a safe relative release file path')
    path = PurePosixPath(name)
    if (path.is_absolute() or name != path.as_posix() or '..' in path.parts
            or name == '.' or '\\' in name or ':' in name):
        raise ValueError(f'Unsafe local change path: {name}')
    return name


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def snapshot_dist(root):
    directory = root / 'dist'
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Expected a real dist directory')
    hashes = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlinks are not release files: {path.relative_to(directory)}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'Expected a regular release file: {path.relative_to(directory)}')
        name = safe_name(path.relative_to(directory).as_posix())
        hashes[name] = digest(path.read_bytes())
    return hashes


def baseline_files(lock):
    files = lock.get('files') if isinstance(lock, dict) else None
    if not isinstance(files, dict) or not valid_hash(lock.get('sha256')):
        raise ValueError('Expected a pinned release SHA-256 and file hashes')
    for name, sha in files.items():
        safe_name(name)
        if not valid_hash(sha):
            raise ValueError(f'Invalid imported file SHA-256: {name}')
    return files


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate local manifest property: {key}')
        result[key] = value
    return result


def local_changes(root, lock):
    path = root / LOCAL_MANIFEST
    if path.is_symlink():
        raise ValueError('Local change manifest must not be a symlink')
    if not path.exists():
        return None
    baseline = baseline_files(lock)
    manifest = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if (not isinstance(manifest, dict) or set(manifest) != {'schemaVersion', 'baseSha256', 'files'}
            or type(manifest['schemaVersion']) is not int or manifest['schemaVersion'] != 1
            or not isinstance(manifest['files'], dict)):
        raise ValueError('Invalid local change manifest schema')
    if manifest['baseSha256'] != lock['sha256']:
        raise ValueError('Local changes belong to a different imported release; import and reapply edits')
    for name, sha in manifest['files'].items():
        safe_name(name)
        if sha is None:
            if name not in baseline:
                raise ValueError(f'Cannot delete an unknown imported file: {name}')
        elif not valid_hash(sha):
            raise ValueError(f'Invalid local file SHA-256: {name}')
    return manifest


def require_entries(files):
    missing = LOCAL_REQUIRED - files.keys()
    if missing:
        raise ValueError('Local edits must keep application entry files: ' + ', '.join(sorted(missing)))


def record_local_changes(root):
    lock = json.loads((root / 'release.lock.json').read_text())
    baseline = baseline_files(lock)
    local_changes(root, lock)  # Reject stale or malformed records before replacing them.
    actual = snapshot_dist(root)
    require_entries(actual)
    changes = {name: actual.get(name) for name in sorted(baseline.keys() | actual.keys())
               if actual.get(name) != baseline.get(name)}
    manifest = {'schemaVersion': 1, 'baseSha256': lock['sha256'], 'files': changes}
    destination = root / LOCAL_MANIFEST
    if changes:
        with tempfile.TemporaryDirectory(prefix='.local-edits-', dir=root) as temporary:
            staging = Path(temporary) / LOCAL_MANIFEST
            staging.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            staging.replace(destination)
        print(f"Recorded {len(changes)} local changes over Synth {lock['version']}; imported release hashes kept")
    else:
        destination.unlink(missing_ok=True)
        print(f"Restored imported Synth {lock['version']}; no local changes")
    return manifest


def check(root):
    lock = json.loads((root / 'release.lock.json').read_text())
    actual = snapshot_dist(root)
    manifest = local_changes(root, lock)
    expected = dict(lock['files'])
    if manifest is not None:
        for name, sha in manifest['files'].items():
            if sha is None:
                expected.pop(name)
            else:
                expected[name] = sha
        require_entries(actual)
    if actual != expected:
        raise ValueError('dist has unrecorded changes; run npm run record:edits or import the pinned ZIP again')
    return lock


def import_release(root, archive):
    if not archive.is_file():
        raise FileNotFoundError(f'Synth release ZIP not found: {archive}')
    sha = digest(archive.read_bytes())
    previous = root / 'release.lock.json'
    old_lock = json.loads(previous.read_text()) if previous.exists() else {}
    version = old_lock.get('version') if old_lock.get('sha256') == sha else f'sha256-{sha[:12]}'
    with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        staging = Path(temporary) / 'dist'
        staging.mkdir()
        hashes = unpack(archive, staging)
        if old_lock.get('sha256') != sha:
            browser = json.loads((staging / BROWSER_RECEIPT).read_text())
            released_version = browser.get('version')
            if isinstance(released_version, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,79}', released_version):
                version = released_version
        lock = {'version': version, 'archive': archive.name, 'sha256': sha, 'files': hashes}
        destination = root / 'dist'
        if destination.exists():
            destination.rename(Path(temporary) / 'previous-dist')
        staging.rename(destination)
        previous.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n')
        (root / LOCAL_MANIFEST).unlink(missing_ok=True)
    print(f'Imported {version}: {len(hashes)} files, SHA256 {sha}')
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', nargs='?', type=Path, help='Path to the Synth release ZIP')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check', action='store_true')
    actions.add_argument('--record-local-changes', action='store_true')
    args = parser.parse_args()
    if (args.check or args.record_local_changes) and args.zip is not None:
        parser.error('choose a ZIP import, --check, or --record-local-changes')
    if not args.check and not args.record_local_changes and args.zip is None:
        parser.error('provide the ZIP path: npm run import:release -- ./xxx.zip')
    try:
        if args.check:
            lock = check(ROOT)
            manifest = local_changes(ROOT, lock)
            if manifest is None:
                print(f"Verified Synth {lock['version']}: {len(lock['files'])} files")
            else:
                print(f"Verified locally edited Synth {lock['version']}: {len(manifest['files'])} recorded local changes over SHA256 {lock['sha256']}")
        elif args.record_local_changes:
            record_local_changes(ROOT)
        else:
            import_release(ROOT, args.zip)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
