"""Supplemental read-only QA of the pinned HIP candidate; not an independent agent verdict."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

source = Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location('hip_archive', source / 'tools/verify_archive.py')
va = importlib.util.module_from_spec(spec)
spec.loader.exec_module(va)


class BoundaryAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        self.contents = {'LICENSE': b'synthetic license fixture'}
        self.contents.update({f'fixture-{i:02d}.md': f'fixture {i}'.encode() for i in range(22)})
        self.files = {p: va.git_blob(b) for p, b in self.contents.items()}
        self.tree = {'truncated': False, 'tree': [
            {'path': p, 'mode': '100644', 'type': 'blob', 'sha': s}
            for p, s in self.files.items()]}
        self.manifest = {'schema_version': 1, 'archive': {
            'repository': va.REPO, 'commit': va.COMMIT, 'files': self.files}}
        (self.root / 'docs/sources.json').write_text(json.dumps(self.manifest))
        self.tree_bytes = json.dumps(self.tree).encode()
        self.calls = []
        self.root_patch = patch.object(va, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.network_patch = patch.object(va, 'urlopen', side_effect=self.response)
        self.network_patch.start()
        self.addCleanup(self.network_patch.stop)

    def response(self, url, timeout):
        self.assertEqual(timeout, 20)
        self.calls.append(url)
        prefix = f'https://api.github.com/repos/{va.REPO}/git/trees/{va.COMMIT}?recursive=1'
        if url == prefix:
            return io.BytesIO(self.tree_bytes)
        prefix = f'https://raw.githubusercontent.com/{va.REPO}/{va.COMMIT}/'
        self.assertTrue(url.startswith(prefix))
        data = self.contents[url[len(prefix):]]
        if isinstance(data, Exception):
            raise data
        return io.BytesIO(data)

    def run_verifier(self):
        with contextlib.redirect_stdout(io.StringIO()):
            va.verify_archive()

    def test_full_positive_fixture(self):
        self.run_verifier()
        self.assertEqual(len(self.calls), 24)

    def test_wrong_blob_rejected(self):
        self.contents['LICENSE'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'Blob mismatch'):
            self.run_verifier()

    def test_oversize_blob_rejected(self):
        self.contents['LICENSE'] = b'x' * (va.LIMIT + 1)
        with self.assertRaisesRegex(ValueError, 'Blob mismatch'):
            self.run_verifier()

    def test_oversize_tree_rejected(self):
        self.tree_bytes = b'x' * (va.LIMIT + 1)
        with self.assertRaisesRegex(ValueError, 'exceeds limit'):
            self.run_verifier()
        self.assertEqual(len(self.calls), 1)

    def test_truncated_tree_stops_before_blob_reads(self):
        self.tree['truncated'] = True
        self.tree_bytes = json.dumps(self.tree).encode()
        with self.assertRaisesRegex(ValueError, 'Incomplete source tree'):
            self.run_verifier()
        self.assertEqual(len(self.calls), 1)

    def test_duplicate_tree_key_rejected(self):
        self.tree_bytes = self.tree_bytes.replace(b'"truncated": false', b'"truncated": false, "truncated": false', 1)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            self.run_verifier()
        self.assertEqual(len(self.calls), 1)

    def test_timeout_fails_closed(self):
        self.contents['LICENSE'] = TimeoutError('fixture timeout')
        with self.assertRaises(TimeoutError):
            self.run_verifier()

    def test_wrong_repository_stops_before_network(self):
        self.manifest['archive']['repository'] = 'invalid/example'
        (self.root / 'docs/sources.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'Unexpected source'):
            self.run_verifier()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
