import copy
import json
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.verify_archive import git_blob, load_manifest, validate_manifest, validate_source_tree, verify_archive

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / 'docs/sources.json').read_text(encoding='utf-8'))['archive']

    def test_exact_license(self):
        self.assertEqual(git_blob((ROOT / 'LICENSE').read_bytes()), '90abd0e6c64a135f42451762337a397bf27f4862')

    def test_license_tamper_detected(self):
        self.assertNotEqual(git_blob((ROOT / 'LICENSE').read_bytes() + b' '), '90abd0e6c64a135f42451762337a397bf27f4862')

    def test_slogans(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('Instructions by design.', readme)
        self.assertIn('Engineer the instructions. Shape the outcome.', readme)

    def test_inventory(self):
        self.assertEqual(len(validate_manifest(self.manifest)), 23)

    def test_source_mismatch(self):
        value = copy.deepcopy(self.manifest)
        value['commit'] = '0' * 40
        with self.assertRaises(ValueError):
            validate_manifest(value)

    def test_missing_license(self):
        value = copy.deepcopy(self.manifest)
        del value['files']['LICENSE']
        with self.assertRaises(ValueError):
            validate_manifest(value)

    def test_path_escape(self):
        value = copy.deepcopy(self.manifest)
        digest = value['files'].pop('README.md')
        value['files']['../README.md'] = digest
        with self.assertRaises(ValueError):
            validate_manifest(value)

    def test_invalid_hash(self):
        value = copy.deepcopy(self.manifest)
        value['files']['README.md'] = 'invalid'
        with self.assertRaises(ValueError):
            validate_manifest(value)

    def source_tree(self):
        return {'truncated': False, 'tree': [
            {'path': path, 'type': 'blob', 'mode': '100644', 'sha': digest}
            for path, digest in self.manifest['files'].items()
        ]}

    def test_exact_source_tree(self):
        validate_source_tree(self.source_tree(), self.manifest['files'])

    def test_substituted_path_same_count(self):
        tree = self.source_tree()
        tree['tree'][0]['path'] = 'unlisted.md'
        with self.assertRaises(ValueError):
            validate_source_tree(tree, self.manifest['files'])

    def test_truncated_tree(self):
        tree = self.source_tree()
        tree['truncated'] = True
        with self.assertRaises(ValueError):
            validate_source_tree(tree, self.manifest['files'])

    def test_duplicate_source_path(self):
        tree = self.source_tree()
        tree['tree'].append(tree['tree'][0].copy())
        with self.assertRaises(ValueError):
            validate_source_tree(tree, self.manifest['files'])

    def test_nonregular_source_entry(self):
        tree = self.source_tree()
        tree['tree'][0]['mode'] = '120000'
        with self.assertRaises(ValueError):
            validate_source_tree(tree, self.manifest['files'])

    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError):
            load_manifest('{"schema_version":1,"schema_version":1}')

    def test_invalid_schema_version(self):
        with self.assertRaises(ValueError):
            load_manifest(json.dumps({'schema_version': True, 'archive': self.manifest}))

    def test_invalid_manifest_type(self):
        with self.assertRaises(ValueError):
            validate_manifest(None)

    def test_nested_duplicate_key(self):
        raw = json.dumps({'schema_version': 1, 'archive': self.manifest})
        raw = raw.replace('"files": {', '"files": {"LICENSE": "' + '0' * 40 + '", ', 1)
        with self.assertRaises(ValueError):
            load_manifest(raw)

    def test_wrong_source_blob(self):
        tree = self.source_tree()
        tree['tree'][0]['sha'] = '0' * 40
        with self.assertRaises(ValueError):
            validate_source_tree(tree, self.manifest['files'])

    def check_manifest_constant(self, token):
        raw = json.dumps({'schema_version': 1, 'archive': self.manifest})
        raw = raw[:-1] + ', "observed_reference": {"value": ' + token + '}}'
        with self.assertRaisesRegex(ValueError, 'Non-JSON numeric constant'):
            load_manifest(raw)

    def test_manifest_nan(self):
        self.check_manifest_constant('NaN')

    def test_manifest_infinity(self):
        self.check_manifest_constant('Infinity')

    def test_manifest_negative_infinity(self):
        self.check_manifest_constant('-Infinity')

    def test_valid_manifest_control(self):
        raw = json.dumps({'schema_version': 1, 'archive': self.manifest,
                          'observed_reference': {'value': 1.25, 'text': 'NaN'}})
        self.assertEqual(load_manifest(raw), self.manifest['files'])

    def check_tree_constant(self, token):
        raw = json.dumps(self.source_tree())[:-1] + ', "observed": ' + token + '}'
        with patch('tools.verify_archive.urlopen', return_value=io.BytesIO(raw.encode())) as request:
            with self.assertRaisesRegex(ValueError, 'Non-JSON numeric constant'):
                verify_archive()
            self.assertEqual(request.call_count, 1)

    def test_tree_nan(self):
        self.check_tree_constant('NaN')

    def test_tree_infinity(self):
        self.check_tree_constant('Infinity')

    def test_tree_negative_infinity(self):
        self.check_tree_constant('-Infinity')
