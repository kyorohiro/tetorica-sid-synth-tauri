import importlib.util
import io
from pathlib import Path
import tempfile
import json
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('importer', Path(__file__).resolve().parents[1] / 'scripts/import_release.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


def release_files(text=b'<html>test</html>'):
    """A small four-core release, with real receipt relationships and no music."""
    files = {name: ('source fixture ' + name).encode() for name in importer.REQUIRED}
    files.update({'index.html': text, 'synth-sid/index.html': text,
                  'synth-sid/synth.js': b'// readable app',
                  'synth-sid/processor.js': b'// processor',
                  'synth-sid/synth.css': b'body {}',
                  'sid-player/processor.js': b'// separate song processor',
                  'js/sid.js': b'// readable wrapper',
                  'js/sid_waveforms.js': b'// pure waveform helpers'})
    original = {'LICENSE': files['LICENSE'],
                'docs/tetorica_sid_synth.webp': files['tetorica_sid_synth.webp']}

    def plain(data):
        return {'bytes': len(data), 'sha256': importer.digest(data)}

    def record(name):
        return {'path': name, **plain(files[name])}

    native = {}
    for component, names in importer.NATIVE_INPUTS.items():
        for name in names:
            # Shared source names must have identical bytes across all kits.
            data = ('native source fixture ' + name).encode()
            original[name] = data
            files[f'sources/{component}/{name}'] = data
        wasm_names = ('sid8580-endpoint.wasm', 'sid8580-machine.wasm') if component == 'sid8580-machine' else (component + '.wasm',)
        for name in wasm_names:
            files[f'generated/{component}/{name}'] = b'\x00asm\x01\x00\x00\x00'
        inputs = {name: plain(original[name]) for name in sorted(names)}
        receipt = {'fixedSdkArtifact': False, 'inputs': inputs}
        if component == 'sid8580-machine':
            receipt.update(format='tetorica-sid8580-research-machine-build', version=1,
                           outputs={name: plain(files[f'generated/{component}/{name}']) for name in wasm_names})
        else:
            receipt.update(schemaVersion=1, component='sid-lab' if component == 'sid' else component,
                           output=plain(files[f'generated/{component}/{component}.wasm']))
        name = f'generated/{component}/{component}-build.json'
        files[name] = json.dumps(receipt).encode(); original['docs/' + name] = files[name]
        native[component] = receipt
        if component != 'sid8580-machine':
            name = f'sources/{component}/README.md'
            original['docs/' + name] = files[name]
    files['LICENSE'] = original['LICENSE']
    for name in importer.REQUIRED_NOTICES:
        data = original.setdefault(name, ('notice fixture ' + name).encode())
        files['sources/sid8580-machine/' + name] = data
    for name in ('LICENSE', 'README.md', 'PATCHES.md'):
        files['licenses/chips-m6581/' + name] = original['third_party/chips-m6581/' + name]
    preview = [record('generated/sid8580-machine/' + name) for name in ('sid8580-endpoint.wasm', 'sid8580-machine.wasm')]
    kit_receipt = {'path': 'sid8580-machine-build.json', **plain(files['generated/sid8580-machine/sid8580-machine-build.json'])}
    files['sources/sid8580-machine/sid8580-machine-build.json'] = files['generated/sid8580-machine/sid8580-machine-build.json']
    notice_roots = ['third_party/sidera/toolchain-notices', 'third_party/sid8580-machine-toolchain-notices']
    files['sources/sid8580-machine/source-kit.json'] = json.dumps({
        'format': 'tetorica-sid-player-8580-source-kit', 'version': 1, 'compiledInputCount': 99,
        'compiledInputs': native['sid8580-machine']['inputs'],
        'sources': {name: plain(original[name]) for name in importer.NATIVE_INPUTS['sid8580-machine'] | importer.REQUIRED_NOTICES},
        'buildReceipt': kit_receipt, 'artifacts': preview, 'noticeRoots': notice_roots,
        'compilerInvocationPerformed': False,
    }).encode()
    entries = sorted(importer.BROWSER_ENTRIES)
    modules = [{**record(name), 'sourcePath': 'docs/' + name, 'localImports':
                ['../js/sid.js'] if name.endswith('/processor.js') else []}
               for name in [*entries, 'js/sid.js', 'js/sid_waveforms.js']]
    original.update({item['sourcePath']: files[item['path']] for item in modules})
    enclosed = io.BytesIO()
    with zipfile.ZipFile(enclosed, 'w') as archive:
        for name, data in original.items():
            archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
    files[importer.BROWSER_SOURCE_ARCHIVE] = enclosed.getvalue()
    files[importer.BROWSER_RECEIPT] = json.dumps({
        'schemaVersion': 1, 'productId': 'tetorica-sid-synth',
        'builder': {'name': 'source-copy', 'minify': False, 'bundle': False},
        'bundles': [record(name) for name in entries], 'modules': modules,
        'originalInputs': [{'path': name, **plain(data)} for name, data in original.items()],
        'sourceArchive': record(importer.BROWSER_SOURCE_ARCHIVE),
        'previewArtifacts': preview,
        'previewSourceKit': {'path': 'sources/sid8580-machine', 'manifest': 'source-kit.json',
                             'compiledInputCount': 99, 'buildReceipt': kit_receipt, 'noticeRoots': notice_roots},
        'songPreviewNativeKits': [{'component': component, 'compiledInputCount': len(importer.NATIVE_INPUTS[component]),
                                   'sourceRoot': 'sources/' + component,
                                   'artifact': record(f'generated/{component}/{component}.wasm'),
                                   'buildReceipt': record(f'generated/{component}/{component}-build.json')}
                                  for component in ('sid-player', 'sid-rsid')],
    }).encode()
    return files

def write_archive(path, files):
    with zipfile.ZipFile(path, 'w') as output:
        for name, data in files.items():
            output.writestr(name, data)


class ImportTests(unittest.TestCase):
    def test_new_zip_updates_without_version_and_preserves_label_for_same_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'any-name.zip'
            write_archive(archive, release_files(b'first'))
            first = importer.import_release(root, archive)
            first['version'] = 'named-release'
            (root / 'release.lock.json').write_text(json.dumps(first))
            self.assertEqual(importer.import_release(root, archive)['version'], 'named-release')
            write_archive(archive, release_files(b'second'))
            changed = importer.import_release(root, archive)
            self.assertNotEqual(changed['sha256'], first['sha256'])
            self.assertEqual(changed['version'], 'sha256-' + changed['sha256'][:12])
            self.assertEqual((root / 'dist/index.html').read_text(), 'second')
            self.assertEqual(importer.check(root), changed)

    def test_validated_browser_version_is_used_without_relying_on_archive_name(self):
        files = release_files()
        receipt = json.loads(files['sources/sid-synth-browser.json'])
        receipt['version'] = '0.0.7'
        files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / 'unrelated-name.zip'
            write_archive(archive, files)
            self.assertEqual(importer.import_release(root, archive)['version'], '0.0.7')

    def test_invalid_replacement_preserves_dist_and_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'release.zip'
            write_archive(archive, release_files(b'valid'))
            first = importer.import_release(root, archive)
            write_archive(archive, {'index.html': b'wrong app'})
            with self.assertRaises(ValueError):
                importer.import_release(root, archive)
            self.assertEqual(importer.check(root), first)
            self.assertEqual((root / 'dist/index.html').read_text(), 'valid')

    def unpack(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'release.zip'
            write_archive(archive, files)
            return importer.unpack(archive, root / 'out')

    def test_preserves_all_original_bytes(self):
        files = release_files()
        self.assertEqual(self.unpack(files), {name: importer.digest(data) for name, data in files.items()})

    def test_check_detects_modified_or_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'dist').mkdir()
            target = root / 'dist/index.html'
            target.write_bytes(b'original')
            (root / 'release.lock.json').write_text(json.dumps({'version': 'test', 'files': {'index.html': importer.digest(b'original')}}))
            self.assertEqual(importer.check(root)['version'], 'test')
            target.write_bytes(b'changed')
            with self.assertRaises(ValueError): importer.check(root)
            target.write_bytes(b'original')
            (root / 'dist/extra.js').write_bytes(b'extra')
            with self.assertRaises(ValueError): importer.check(root)

    def test_rejects_traversal(self):
        for name in ['../escape', '/absolute', 'a/../../escape', 'a\\escape', 'C:/escape',
                     './index.html', 'a//b', 'a/./b', 'a\nb']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.unpack({name: b'bad'})

    def test_rejects_wrong_release_or_missing_wasm_and_sources(self):
        with self.assertRaises(ValueError): self.unpack({'index.html': b'wrong app'})
        for name in [*(f'generated/{component}/{component}-build.json' for component in importer.NATIVE_INPUTS),
                     'generated/sid/sid.wasm', 'generated/sid-player/sid-player.wasm',
                     'generated/sid-rsid/sid-rsid.wasm', 'generated/sid8580-machine/sid8580-endpoint.wasm',
                     'generated/sid8580-machine/sid8580-machine.wasm', importer.BROWSER_SOURCE_ARCHIVE]:
            files = release_files(); del files[name]
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)

    def test_rejects_mismatched_receipts_and_changed_native_or_browser_bytes(self):
        for name in ['generated/sid/sid.wasm', 'generated/sid-player/sid-player.wasm',
                     'generated/sid-rsid/sid-rsid.wasm', 'generated/sid8580-machine/sid8580-endpoint.wasm',
                     'synth-sid/synth.js', 'js/sid.js', 'js/sid_waveforms.js',
                     'sources/sid/tetorica_src/wasm/sid_core.h',
                     'sources/sid8580-machine/third_party/sidera/adapted/src/envelope.rs',
                     importer.BROWSER_SOURCE_ARCHIVE]:
            files = release_files(); files[name] = b'changed'
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        receipt = json.loads(files[importer.BROWSER_RECEIPT]); receipt['productId'] = 'tetorica-spu-synth'
        files[importer.BROWSER_RECEIPT] = json.dumps(receipt).encode()
        with self.assertRaises(ValueError): self.unpack(files)

    def test_every_readable_module_matches_its_live_bytes_and_original_input_record(self):
        files = release_files()
        receipt = json.loads(files['sources/sid-synth-browser.json'])
        receipt['modules'][-1]['sha256'] = '0' * 64
        files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/sid-synth-browser.json'])
        receipt['originalInputs'][-1]['sha256'] = '0' * 64
        files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'original source'): self.unpack(files)

    def test_readable_module_graph_cannot_omit_a_dependency_or_an_entry(self):
        for omitted in ['js/sid.js', 'synth-sid/synth.js']:
            files = release_files()
            receipt = json.loads(files['sources/sid-synth-browser.json'])
            receipt['modules'] = [item for item in receipt['modules'] if item['path'] != omitted]
            files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(omitted=omitted), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        del files['js/sid.js']
        with self.assertRaisesRegex(ValueError, 'Missing recorded'): self.unpack(files)

    def test_all_four_native_kits_require_exact_rebuild_inputs_and_receipts(self):
        for component, inputs in importer.NATIVE_INPUTS.items():
            name = sorted(inputs)[-1]
            files = release_files(); del files[f'sources/{component}/{name}']
            with self.subTest(component=component, kind='missing source'), self.assertRaises(ValueError): self.unpack(files)
            files = release_files(); path = f'generated/{component}/{component}-build.json'
            receipt = json.loads(files[path]); del receipt['inputs'][name]; files[path] = json.dumps(receipt).encode()
            with self.subTest(component=component, kind='edited receipt'), self.assertRaises(ValueError): self.unpack(files)
        files = release_files(); path = 'sources/sid8580-machine/source-kit.json'
        receipt = json.loads(files[path]); del receipt['compiledInputs'][next(iter(receipt['compiledInputs']))]
        files[path] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'compiled inputs'): self.unpack(files)

    def test_readable_builder_and_complete_license_notices_are_required(self):
        for builder in [None, {'name': 'esbuild', 'minify': False, 'bundle': False},
                        {'name': 'source-copy', 'minify': True, 'bundle': False},
                        {'name': 'source-copy', 'minify': False, 'bundle': True}]:
            files = release_files(); receipt = json.loads(files[importer.BROWSER_RECEIPT]); receipt['builder'] = builder
            files[importer.BROWSER_RECEIPT] = json.dumps(receipt).encode()
            with self.subTest(builder=builder), self.assertRaisesRegex(ValueError, 'source-copy'): self.unpack(files)
        for name in ['licenses/chips-m6581/LICENSE', 'sources/sid/third_party/chips-m6581/LICENSE',
                     'sources/sid-player/third_party/chips-m6502/LICENSE',
                     'sources/sid-rsid/third_party/chips-c64/LICENSE',
                     'sources/sid8580-machine/third_party/sidera/LICENSE',
                     'sources/sid8580-machine/third_party/sidera/toolchain-notices/licenses/MIT.txt',
                     'sources/sid8580-machine/third_party/sid8580-machine-toolchain-notices/musl-COPYRIGHT.txt']:
            files = release_files(); del files[name]
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)
        files = release_files(); files['licenses/chips-m6581/LICENSE'] = b'changed notice'
        with self.assertRaises(ValueError): self.unpack(files)

    def test_no_user_music_firmware_extra_modules_or_uninspected_archives(self):
        for name in ['songs/demo.sid', 'roms/kernal.bin', 'roms/basic.rom', 'recording.wav',
                     'sources/extra.zip', 'js/unrecorded.js']:
            files = release_files(); files[name] = b'not an app source'
            with self.subTest(name=name), self.assertRaises(ValueError): self.unpack(files)

    def test_enclosed_browser_sources_match_every_original_input_record(self):
        for mode in ['changed', 'missing', 'extra', 'unsafe', 'duplicate']:
            files = release_files()
            receipt = json.loads(files['sources/sid-synth-browser.json'])
            with zipfile.ZipFile(io.BytesIO(files[importer.BROWSER_SOURCE_ARCHIVE])) as source:
                original = {name: source.read(name) for name in source.namelist()}
            if mode == 'changed': original['docs/synth-sid/synth.js'] = b'other original code'
            if mode == 'missing': original.pop('docs/synth-sid/synth.js')
            if mode == 'extra': original['extra.js'] = b'not recorded'
            if mode == 'unsafe': original['../escape.js'] = b'unsafe path'
            enclosed = io.BytesIO()
            with zipfile.ZipFile(enclosed, 'w') as archive:
                for name, data in original.items(): archive.writestr(name, data)
                if mode == 'duplicate':
                    with self.assertWarns(UserWarning): archive.writestr('docs/synth-sid/synth.js', b'duplicate')
            data = enclosed.getvalue(); files['sources/sid-synth-browser-inputs.zip'] = data
            receipt['sourceArchive'].update(bytes=len(data), sha256=importer.digest(data))
            files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.unpack(files)

    def test_malformed_or_unsafe_module_records_are_rejected(self):
        for replacement in [[], [None], [{'path': '../escape'}]]:
            files = release_files()
            receipt = json.loads(files['sources/sid-synth-browser.json']); receipt['modules'] = replacement
            files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): self.unpack(files)
        files = release_files()
        receipt = json.loads(files['sources/sid-synth-browser.json'])
        receipt['modules'][0]['localImports'] = ['../../escape.js']
        files['sources/sid-synth-browser.json'] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(ValueError, 'Unsafe'): self.unpack(files)

    def test_rejects_duplicate_names_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / 'release.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('index.html', b'a')
                with self.assertWarns(UserWarning): output.writestr('index.html', b'b')
            with self.assertRaisesRegex(ValueError, 'Duplicate'): importer.unpack(archive, root / 'out')
            with zipfile.ZipFile(archive, 'w') as output:
                info = zipfile.ZipInfo('link'); info.create_system = 3
                info.external_attr = 0o120777 << 16
                output.writestr(info, '../../escape')
            with self.assertRaisesRegex(ValueError, 'Unsafe'): importer.unpack(archive, root / 'out2')


if __name__ == '__main__':
    unittest.main()
