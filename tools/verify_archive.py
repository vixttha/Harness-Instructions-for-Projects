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


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def load_manifest(raw):
    document = json.loads(raw, object_pairs_hook=strict_object)
    if (not isinstance(document, dict)
            or type(document.get('schema_version')) is not int
            or document['schema_version'] != 1):
        raise ValueError('Unexpected manifest schema')
    return validate_manifest(document.get('archive'))


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'repository', 'commit', 'files'}:
        raise ValueError('Invalid archive manifest')
    if manifest['repository'] != REPO or manifest['commit'] != COMMIT:
        raise ValueError('Unexpected source')
    files = manifest['files']
    if not isinstance(files, dict) or len(files) != 23 or 'LICENSE' not in files:
        raise ValueError('Incomplete inventory')
    for path, digest in files.items():
        if (not isinstance(path, str) or not isinstance(digest, str)
                or not re.fullmatch(r'[A-Za-z0-9._/-]+', path)
                or any(p in ('', '.', '..') for p in path.split('/'))
                or not re.fullmatch(r'[0-9a-f]{40}', digest)):
            raise ValueError('Invalid path or digest')
    return files


def validate_source_tree(tree, files):
    if (not isinstance(tree, dict) or tree.get('truncated') is not False
            or not isinstance(tree.get('tree'), list)):
        raise ValueError('Incomplete source tree')
    paths = set()
    actual = {}
    for entry in tree['tree']:
        path = entry.get('path')
        if not isinstance(path, str) or path in paths:
            raise ValueError('Invalid or duplicate source path')
        paths.add(path)
        if entry.get('type') == 'tree' and entry.get('mode') == '040000':
            continue
        if entry.get('type') != 'blob' or entry.get('mode') not in ('100644', '100755'):
            raise ValueError(f'Unsupported source entry: {path}')
        actual[path] = entry.get('sha')
    if actual != files:
        raise ValueError('Pinned source tree differs from manifest')


def verify_archive():
    files = load_manifest((ROOT / 'docs/sources.json').read_text(encoding='utf-8'))
    url = f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1'
    with urlopen(url, timeout=20) as response:
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Source tree response exceeds limit')
    validate_source_tree(json.loads(raw, object_pairs_hook=strict_object), files)
    print(f'Complete pinned source tree matches {len(files)} manifest paths.')
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
