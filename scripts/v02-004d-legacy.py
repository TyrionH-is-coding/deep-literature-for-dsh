"""Retain a real baseline interruption, then explicitly resume it after the fix."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location('probe', Path(__file__).with_name('v02-004d-probe.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def main():
    mode, directory = sys.argv[1:]
    root = Path(directory).resolve()
    if mode == 'baseline':
        result = p.scenario(root, 'parse-kill-before')
        assert result['final']['state'] == 'failed'
        assert result['final']['last_error'] == 'generation_workspace_conflict'
        assert not result['live_owned_processes']
        p.record_provenance(root / 'legacy-provenance.json')
        checkpoints = {str(f.relative_to(root)): {'sha256':p.sha(f), 'value':p.read(f)} for f in root.glob('data/papers/**/job.json')}
        p.atomic_write_json(root / 'legacy-original-checkpoints.json', checkpoints)
        for relative, item in checkpoints.items():
            target=root / 'legacy-original-files' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / relative).read_bytes())
            assert p.sha(target)==item['sha256']
        print(json.dumps(result, indent=2))
        return
    assert mode == 'resume'
    p.record_provenance(root / 'resume-provenance.json')
    before = p.read(root / 'result.json')
    original=p.read(root / 'legacy-original-checkpoints.json')
    assert all(p.sha(root / f)==v['sha256'] for f,v in original.items())
    config = p.read(root / 'config.json')
    store = p.BackgroundJobStore(root / 'data')
    parent = config['parent']
    pipeline = p.ReadingPipeline(root / 'data')
    assert pipeline.start(config['paper']).parent_job_id == parent
    generation = root / 'data/papers' / config['paper'] / 'generations' / before['final']['source_pdf_sha256'][:16]
    checkpoint = p.read(generation / 'job.json')
    assert 'source_sha256' not in checkpoint['stages']['paper_parse_upgrade']['result']
    supplied = {}
    processes = []
    for attempt in range(12):
        p.atomic_write_json(root / 'input.json', supplied)
        with (root / f'resume-{attempt}.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen([sys.executable, '-I', '-X', 'utf8', str(Path(p.__file__)), '--worker', str(root)],
                stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            identity = p.process_start_identity(child.pid)
            try:
                code = child.wait(timeout=45)
            finally:
                active = p.read(root / 'active-process.json')
                if store._pid_is_alive(active['pid']) and p.process_start_identity(active['pid']) == active['identity']:
                    os.kill(active['pid'], p.signal.SIGTERM)
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=8)
            processes.append(dict(pid=child.pid, identity=identity, worker=active, exit=code,
                alive=store._pid_is_alive(child.pid), worker_alive=store._pid_is_alive(active['pid'])))
        status = store.load_status(parent)
        if status.state == 'completed':
            break
        assert status.state == 'waiting_agent', status.to_dict()
        required = status.required_input
        if status.reason_code == 'review_full_read':
            supplied = {'full_review': p._review(required)}
        else:
            supplied = {'full_translation': p._translation(p.read(Path(required['source_manifest_path'])))}
    derived = []
    for marker in (root / 'data').glob('jobs/*/launch.json'):
        value = p.read(marker)
        deadline = time.monotonic() + 20
        while store._pid_is_alive(value['pid']) and time.monotonic() < deadline:
            time.sleep(.05)
        derived.append(dict(marker=value, alive=store._pid_is_alive(value['pid'])))
    result = dict(parent=parent, final=pipeline.inspect(parent).to_dict(), processes=processes,
                  derived=derived, legacy_checkpoint=checkpoint, originalCheckpoints=original, assets=p.assets(root))
    p.atomic_write_json(root / 'resume-result.json', result)
    assert result['final']['state'] == 'completed'
    assert pipeline.start(config['paper']).parent_job_id == parent
    assert all(not x['alive'] and not x['worker_alive'] for x in processes)
    assert all(not x['alive'] for x in derived)
    assert not list((root / 'data').glob('jobs/**/owner.json'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
