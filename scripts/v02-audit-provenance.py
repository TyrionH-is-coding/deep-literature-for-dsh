"""Compare fixed release members, rebuilt members, and Git blobs without extraction.

Run after npm run build:ci and npm pack --ignore-scripts --pack-destination outputs/v02-audit.
Byte hashes remain authoritative; text EOL equivalence is reported separately.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile
import difflib

ROOT = Path(__file__).resolve().parents[1]
BASE = '8e00b334389cd90721b7d404013a07687753aa5c'
EXPECTED = '318814ec542de94a47cd2855b21d0f7af9778b22b283d3995d0c499a3465e2fd'
OUT = ROOT / 'docs/codex-v02/evidence'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def tar_members(path):
    with tarfile.open(path) as archive:
        return {m.name.removeprefix('package/'): archive.extractfile(m).read()
                for m in archive.getmembers() if m.isfile()}

def zip_members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}

def comparison(left, right):
    rows = []
    for name in sorted(set(left) | set(right)):
        a, b = left.get(name), right.get(name)
        state = 'missing-left' if a is None else 'missing-right' if b is None else 'exact' if a == b else 'different'
        if state == 'different':
            try:
                if a.decode('utf-8').replace('\r\n', '\n') == b.decode('utf-8').replace('\r\n', '\n'):
                    state = 'text-eol-only'
            except UnicodeDecodeError:
                pass
        rows.append({'path': name, 'state': state, 'leftSHA256': sha(a) if a is not None else None, 'rightSHA256': sha(b) if b is not None else None})
    return {'counts': {s: sum(r['state'] == s for r in rows) for s in sorted({r['state'] for r in rows})}, 'files': rows}

release_path = ROOT / 'outputs/v02-audit/scientific-reading.tgz'
rebuilt_path = ROOT / 'outputs/v02-audit/dsh-external-dsh-scientific-reading-0.1.0-rc.5.tgz'
assert sha(release_path.read_bytes()) == EXPECTED
release, rebuilt = tar_members(release_path), tar_members(rebuilt_path)
wheel_names = [n for n in release if n.endswith('.whl')]
assert len(wheel_names) == 1
wheel_name = wheel_names[0]
released_wheel, rebuilt_wheel = zip_members(release[wheel_name]), zip_members(rebuilt[wheel_name])
paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE], cwd=ROOT, text=True).splitlines()
git_python = {}
git_assets = {}
for path in paths:
    if path.startswith('engine/src/scientific_reading/') and path.endswith('.py'):
        target = path.removeprefix('engine/src/')
    elif path.startswith('engine/reader/') and path.endswith('.py'):
        target = path.removeprefix('engine/')
    else:
        target = None
    if target is not None:
        git_python[target] = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    if path in release:
        git_assets[path] = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
result = {
    'baseCommit': BASE, 'releaseSHA256': EXPECTED,
    'rebuiltSHA256': sha(rebuilt_path.read_bytes()),
    'releaseVsRebuiltTarMembers': comparison(release, rebuilt),
    'releaseVsRebuiltWheelMembers': comparison(released_wheel, rebuilt_wheel),
    'releasePythonVsGitBlobs': comparison({n: b for n, b in released_wheel.items() if n.endswith('.py')}, git_python),
    'releaseTrackedAssetsVsGitBlobs': comparison({n: release[n] for n in git_assets}, git_assets),
}
(OUT / 'provenance.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
details = []
for name in sorted(set(released_wheel) & set(rebuilt_wheel)):
    a, b = released_wheel[name], rebuilt_wheel[name]
    if a != b:
        details.append(f'{name}: release={sha(a)} rebuilt={sha(b)}\n')
        details.extend(difflib.unified_diff(
            a.decode('utf-8').replace('\r\n', '\n').splitlines(True),
            b.decode('utf-8').replace('\r\n', '\n').splitlines(True),
            fromfile='release/' + name, tofile='rebuilt/' + name, n=0))
with zipfile.ZipFile(io.BytesIO(release[wheel_name])) as a, zipfile.ZipFile(io.BytesIO(rebuilt[wheel_name])) as b:
    details.append(f'First ZIP member timestamps: release={a.infolist()[0].date_time}, rebuilt={b.infolist()[0].date_time}\n')
(OUT / 'wheel-differences.log').write_text(''.join(details), encoding='utf-8')
for key, value in result.items():
    print(key, value['counts'] if isinstance(value, dict) else value)
