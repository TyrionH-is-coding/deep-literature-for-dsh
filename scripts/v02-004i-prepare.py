"""Install an exact source copy in this card's venv, then deny networking."""
import hashlib
import json
import pathlib
import shutil
import sys
import sysconfig

repo = pathlib.Path(__file__).resolve().parents[1]
assert pathlib.Path(sys.prefix).resolve() == repo / '.venv'
assert sys.version_info[:3] == (3, 11, 16)
site = pathlib.Path(sysconfig.get_paths()['purelib'])
hashes = {}
for name, source in [('scientific_reading', repo/'engine/src/scientific_reading'), ('reader', repo/'engine/reader')]:
    dest = site/name
    shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    for file in source.rglob('*.py'):
        relative = file.relative_to(source)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        assert digest == hashlib.sha256((dest/relative).read_bytes()).hexdigest()
        hashes[name+'/'+relative.as_posix()] = digest
(site/'sitecustomize.py').write_text("import socket\ndef deny(*a, **k):\n    raise RuntimeError('v02_004i_network_forbidden')\nsocket.socket.connect = deny\nsocket.create_connection = deny\n", encoding='utf-8')
output = repo/'docs/codex-v02/V02-004I-evidence'
output.mkdir(exist_ok=True)
(output/'environment.json').write_text(json.dumps({'python': sys.version, 'executable': sys.executable,
    'site': str(site), 'source_sha256': hashes, 'network': 'socket connections denied',
    'mode': 'source-copy integration, not installed-product acceptance'}, indent=2), encoding='utf-8')
print('Verified exact Python sources:', len(hashes))
