"""Run every Python test once against one source snapshot, in isolated shards."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def run(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / 'engine/tests').glob('test_*.py'))
    process = [p for p in files if p.name == 'test_reading_control_process.py']
    recovery = [p for p in files if p.name in {'test_v02_parse_recovery.py', 'test_v02_pipeline_contract.py'}]
    other = [p for p in files if p not in process + recovery]
    groups = dict(control_process=process, original_recovery=recovery, regression_a=other[::2], regression_b=other[1::2])
    assigned = [p for group in groups.values() for p in group]
    assert len(assigned) == len(set(assigned)) == len(files)
    assert set(assigned) == set(files)
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    changed = subprocess.check_output(['git', 'diff', '--name-only', 'a37a415c4bec9a895f1dc1619cfa35081cf85d26', 'HEAD', '--', 'engine', 'scripts'], cwd=ROOT, text=True).splitlines()
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in changed}
    run_root = Path(tempfile.mkdtemp(prefix='v4f-suite-', dir='C:/tmp')).resolve()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('SR_SCOPE', 'MINERU_', 'FEISHU_', 'SR_SCANSCI', 'SCANSCI_')):
            env.pop(key)
    env.update(PYTHONPATH=os.pathsep.join([str(ROOT / 'engine/src'), str(ROOT / 'engine')]),
               PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', SR_NATIVE_KEYRING_TEST='0',
               V02_004F_EVIDENCE=str(output / 'processes'))
    result = dict(sourceCommit=source_commit, sourceHashes=hashes, runRoot=str(run_root),
                  executable=sys.executable, startedAt=time.time(), shards={})
    children = []
    for name, group in groups.items():
        basetemp = (run_root / name).resolve()
        assert basetemp.parent == run_root and not basetemp.exists()
        command = [sys.executable, '-m', 'pytest', *[str(p.relative_to(ROOT)) for p in group], '-vv', '-rs',
                   '-o', 'faulthandler_timeout=120', '--basetemp', str(basetemp),
                   '--junitxml=' + str(output / (name + '.xml'))]
        with (output / (name + '.log')).open('w', encoding='utf-8') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result['shards'][name] = dict(command=command, files=[str(p.relative_to(ROOT)) for p in group], pid=child.pid)
        children.append((name, child))
    (output / 'run.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    for name, child in children:
        code = child.wait()
        shard = result['shards'][name]
        shard['exitCode'] = code
        xml_path = output / (name + '.xml')
        if xml_path.exists():
            root = ET.parse(xml_path).getroot()
            suites = [root] if root.tag == 'testsuite' else root.findall('testsuite')
            shard['counts'] = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    result['sourceUnchanged'] = all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    result['finishedAt'] = time.time()
    result['totals'] = {key: sum(s.get('counts', {}).get(key, 0) for s in result['shards'].values()) for key in ('tests', 'failures', 'errors', 'skipped')}
    result['passed'] = result['totals']['tests'] - sum(result['totals'][k] for k in ('failures', 'errors', 'skipped'))
    result['allPassed'] = result['sourceUnchanged'] and all(s['exitCode'] == 0 for s in result['shards'].values())
    (output / 'run.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('sourceCommit', 'sourceUnchanged', 'totals', 'passed', 'allPassed', 'runRoot')}, indent=2))
    return 0 if result['allPassed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
