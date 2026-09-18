"""Copy frozen source into a task-only venv; no checkout overlay or user install."""
import hashlib, io, json, pathlib, shutil, sys, sysconfig, zipfile
repo = pathlib.Path(__file__).resolve().parents[1]
site = pathlib.Path(sysconfig.get_paths()['purelib'])
assert sys.prefix != sys.base_prefix
assert 'v004g-env' in sys.prefix
hashes = {}
for name, source in [('scientific_reading', repo/'engine/src/scientific_reading'), ('reader', repo/'engine/reader')]:
    dest = site/name
    shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    for file in source.rglob('*.py'):
        relative = file.relative_to(source)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        assert digest == hashlib.sha256((dest/relative).read_bytes()).hexdigest()
        hashes[name+'/'+relative.as_posix()] = digest
# Defense for every task Python process, including production-launched workers.
(site/'sitecustomize.py').write_text("import socket\ndef deny(*a, **k):\n    raise RuntimeError('v004g_network_forbidden')\nsocket.socket.connect = deny\nsocket.create_connection = deny\n", encoding='utf-8')
import pip._vendor.distlib
launcher = pathlib.Path(pip._vendor.distlib.__file__).parent/'t64.exe'
archive = io.BytesIO()
with zipfile.ZipFile(archive,'w') as z:
    z.writestr('__main__.py', (repo/'scripts/fixtures/v02-004g/provider.py').read_text(encoding='utf-8-sig'))
exe = pathlib.Path(sys.prefix)/'Scripts/v004g-provider.exe'
exe.write_bytes(launcher.read_bytes() + ('#!'+sys.executable+'\n').encode() + archive.getvalue())
(repo/'docs/codex-v02/V02-004G-evidence/environment.json').write_text(json.dumps({'python':sys.version,'executable':sys.executable,'source_sha256':hashes,'provider_exe':str(exe),'provider_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'sitecustomize':'socket connect denied; no other patch','mode':'exact source copy, not wheel/install acceptance'},indent=2),encoding='utf-8')
print('verified source files:',len(hashes))
