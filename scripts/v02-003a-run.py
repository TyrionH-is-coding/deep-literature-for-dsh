"""Reproducible local verification; all outputs belong to this checkout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/codex-v02/V02-003A-evidence'
PYTHON = ROOT / '.venv/Scripts/python.exe'
INSTALL = ROOT / 'outputs/v02-003a/installed-env'
ENV = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
    PYTHONPATH=os.pathsep.join([str(ROOT / 'engine/src'), str(ROOT / 'engine')]),
    SCIENTIFIC_READING_PYTHON=str(PYTHON),
    PIP_CONSTRAINT=str(ROOT / 'docs/codex-v02/evidence/audit-python-requirements.txt'))
RUNS = []

def run(name, command, env=ENV):
    start = time.time()
    result = subprocess.run([str(arg) for arg in command], cwd=ROOT, env=env,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
    (EVIDENCE / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    RUNS.append(dict(name=name, command=[str(arg) for arg in command], cwd=str(ROOT),
        exit_code=result.returncode, seconds=round(time.time()-start, 3)))
    (EVIDENCE / 'runs.json').write_text(json.dumps(RUNS, indent=2), encoding='utf-8')
    print(name, result.returncode, flush=True)
    if result.returncode:
        print(result.stdout + result.stderr)
        raise SystemExit(result.returncode)

run('targeted', [PYTHON, '-m', 'pytest', 'engine/tests/test_xlsx_snapshot.py',
    'engine/tests/test_worker_xlsx_snapshot.py', 'engine/tests/test_pipeline_excel_end_to_end.py',
    '-q', '--tb=short', '--junitxml=' + str(EVIDENCE / 'targeted-junit.xml')])
run('wheel-build', ['node', 'scripts/build-engine.mjs'])
run('typescript-build', ['node', 'node_modules/typescript/bin/tsc', '-p', 'tsconfig.json'])
run('excel-actions', ['node', 'tests/excel-actions.mjs'])
run('source-smoke', [PYTHON, 'scripts/v02-003a-smoke.py'])
assert not INSTALL.exists(), 'Use a fresh isolated install directory'
run('installed-venv', [PYTHON, '-m', 'venv', INSTALL])
installed_python = INSTALL / 'Scripts/python.exe'
clean = ENV.copy()
clean.pop('PYTHONPATH', None)
clean['SCIENTIFIC_READING_PYTHON'] = str(installed_python)
run('installed-dependencies', [installed_python, '-m', 'pip', 'install', '-r',
    'docs/codex-v02/evidence/audit-python-requirements.txt'], clean)
wheels = list((ROOT / 'dist/python').glob('*.whl'))
assert len(wheels) == 1
run('installed-wheel', [installed_python, '-m', 'pip', 'install', '--no-deps', wheels[0]], clean)
run('installed-smoke', [installed_python, 'scripts/v02-003a-smoke.py', '--installed'], clean)
run('installed-freeze', [installed_python, '-m', 'pip', 'freeze', '--all'], clean)
run('python-version', [PYTHON, '--version'])
run('node-version', ['node', '--version'])
summary = dict(wheel=str(wheels[0]), sha256=hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
    bytes=wheels[0].stat().st_size, requirements_sha256=hashlib.sha256(
        (ROOT / 'docs/codex-v02/evidence/audit-python-requirements.txt').read_bytes()).hexdigest(),
    source={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / 'engine/src/scientific_reading').glob('xlsx*.py')})
(EVIDENCE / 'artifact.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
