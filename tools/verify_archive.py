"""Read-only verification of a pinned historical snapshot; no imported code execution."""
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REPO = 'vixttha/Blender-Agent-Refinement-Toolkit'
COMMIT = 'b63b7b68495abcce76dfbc4341aa149ea15e0049'
LIMIT = 1024 * 1024


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def validate_manifest(manifest):
    if manifest['repository'] != REPO or manifest['commit'] != COMMIT:
        raise ValueError('Unexpected source')
    files = manifest['files']
    if len(files) != 23 or 'LICENSE' not in files:
        raise ValueError('Incomplete inventory')
    for path, digest in files.items():
        if (not re.fullmatch(r'[A-Za-z0-9._/-]+', path)
                or any(p in ('', '.', '..') for p in path.split('/'))
                or not re.fullmatch(r'[0-9a-f]{40}', digest)):
            raise ValueError('Invalid path or digest')
    return files


def verify_archive():
    manifest = json.loads((ROOT / 'docs/sources.json').read_text(encoding='utf-8'))['archive']
    files = validate_manifest(manifest)
    for path, digest in sorted(files.items()):
        url = f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}'
        with urlopen(url, timeout=20) as response:
            data = response.read(LIMIT + 1)
        if len(data) > LIMIT or git_blob(data) != digest:
            raise ValueError(f'Blob mismatch: {path}')
        print(f'{digest}  {path}')
    print(f'Verified {len(files)} source blobs at {COMMIT}; no files migrated.')


if __name__ == '__main__':
    verify_archive()
