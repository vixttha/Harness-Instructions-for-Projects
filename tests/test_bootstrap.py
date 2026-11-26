import copy
import json
from pathlib import Path
import unittest
from tools.verify_archive import git_blob, validate_manifest

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
