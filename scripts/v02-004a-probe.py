"""Bounded synthetic pipeline probe; no production overlay or network services.

Run with the task venv. Each worker is a new hidden Python process. Only the
MinerU provider is replaced; stage runner, parse service, translation, renderer,
publication, job store, worker and derived launcher remain real.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "engine/src"), str(REPO / "engine"), str(REPO / "scripts")]
from verify_full_read_pipeline import _metadata, _fixture_pdf, _translation, _review
from scientific_reading.background_store import BackgroundJobStore, JobClaimUnavailable
from scientific_reading.background_launcher import process_start_identity
from scientific_reading.full_read_service import FullReadService
from scientific_reading.library_service import LibraryService
from scientific_reading.mineru_service import MineruParseService
from scientific_reading.mineru_provider import ProviderResult
from scientific_reading.reading_pipeline import ReadingPipeline
from scientific_reading.worker import run_job, full_read_pipeline_handler_factory
from scientific_reading.workspace import PaperWorkspace, atomic_write_json

SCENARIOS = ('parse-fail-before', 'parse-kill-before', 'parse-kill-after',
             'translation-fail-after', 'translation-kill-after', 'baseline')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(root, name, **values):
    with (root / 'calls.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(dict(name=name, pid=os.getpid(), **values)) + '\n')


def fault(root, boundary):
    scenario = read(root / 'config.json')['scenario']
    if not scenario.startswith(boundary) or (root / 'fault-fired.json').exists():
        return
    atomic_write_json(root / 'fault-fired.json', dict(scenario=scenario, pid=os.getpid()))
    if '-fail-' in scenario:
        raise RuntimeError('controlled_' + scenario.replace('-', '_'))
    atomic_write_json(root / 'blocked.json', dict(pid=os.getpid(), identity=process_start_identity(os.getpid())))
    while True:
        time.sleep(.05)


class Provider:
    provider_id = 'mineru-local-v1'
    version = 'v02-004a-fixture'

    def __init__(self, root):
        self.root = root

    def parse(self, pdf, staging, method, heartbeat):
        event(self.root, 'provider_parse')
        staging.mkdir(parents=True)
        content = [dict(type='header', text=_metadata().title, text_level=1, page_idx=0, bbox=[72, 72, 520, 110])]
        content += [dict(type='text', text=f'Synthetic engineering paragraph {i} on load and deflection.',
                        page_idx=i // 12, bbox=[72, 120, 520, 145]) for i in range(42)]
        atomic_write_json(staging / 'fixture_content_list.json', content)
        if read(self.root / 'config.json')['scenario'].endswith('before'):
            fault(self.root, 'parse-')
        return ProviderResult(self.provider_id, self.version, staging)


class Parse(MineruParseService):
    def __init__(self, root):
        super().__init__(provider_factory=lambda *_: Provider(root))
        self.root = root

    def run(self, *args, **kwargs):
        result = super().run(*args, **kwargs)
        event(self.root, 'parse_service', cached=result.cached)
        if read(self.root / 'config.json')['scenario'].endswith('after'):
            fault(self.root, 'parse-')
        return result


class Full(FullReadService):
    def __init__(self, root):
        super().__init__()
        self.root = root

    def save_translation_batch(self, workspace, value):
        path = workspace.reading_dir / 'full/batches' / (value['batch_id'] + '.translation.json')
        existed = path.exists()
        result = super().save_translation_batch(workspace, value)
        event(self.root, 'translation_save', batch=value['batch_id'], existed=existed, sha=sha(result))
        fault(self.root, 'translation-')
        return result


def worker(root):
    atomic_write_json(root / 'active-process.json', dict(pid=os.getpid(), identity=process_start_identity(os.getpid())))
    # Fail closed for accidental Python networking. No real provider is selected.
    def forbidden(*args, **kwargs):
        raise AssertionError('v02_004a_network_forbidden')
    socket.socket.connect = forbidden
    socket.create_connection = forbidden
    config = read(root / 'config.json')
    store = BackgroundJobStore(root / 'data')
    pipeline = ReadingPipeline(root / 'data', mineru_service=Parse(root), full_read_service=Full(root))
    before = store.load_status(config['parent']).to_dict()
    pipeline.inspect(config['parent'])
    event(root, 'worker_loaded', before=before, after=store.load_status(config['parent']).to_dict())
    if store.load_status(config['parent']).state in {'failed', 'interrupted', 'waiting_agent', 'waiting_user'}:
        store.transition(config['parent'], 'queued')
    supplied = read(root / 'input.json')
    return run_job(store, config['parent'], {'full_read_pipeline':
        full_read_pipeline_handler_factory(pipeline, pipeline_input=supplied)})


def assets(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.glob('data/papers/**/*'))
            if p.is_file() and (p.name in {'source_map.json', 'full.md', 'reader.html', 'reader_manifest.json'}
                                or p.name.endswith('.translation.json'))}


def scenario(root, name):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    data = root / 'data'
    library = LibraryService(data)
    try:
        paper = library.ingest(_metadata())['paper_id']
    finally:
        library.close()
    workspace = PaperWorkspace.create_for_paper_id(data, paper, _metadata())
    _fixture_pdf(workspace.source_pdf)
    pipeline = ReadingPipeline(data)
    first = pipeline.start(paper)
    parent = first.parent_job_id
    assert pipeline.start(paper).parent_job_id == parent
    atomic_write_json(root / 'config.json', dict(scenario=name, parent=parent, paper=paper))
    store = pipeline.job_store
    result = dict(scenario=name, root=str(root), parent=parent, processes=[], snapshots=[], attempts=[])
    supplied = None
    protected = {}
    env = os.environ.copy()
    # Children (including real xlsx worker) use only this checkout and task venv.
    env['PYTHONPATH'] = os.pathsep.join([str(REPO / 'engine/src'), str(REPO / 'engine')])
    env['SR_NATIVE_KEYRING_TEST'] = '0'
    for key in list(env):
        if key.startswith(('SR_SCOPE', 'MINERU_', 'FEISHU_', 'SR_SCANSCI', 'SCANSCI_')):
            env.pop(key)
    for attempt in range(14):
        atomic_write_json(root / 'input.json', supplied)
        log = root / f'worker-{attempt}.log'
        with log.open('w', encoding='utf-8') as out:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(root)],
                env=env, stdout=out, stderr=out, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            proc = dict(pid=child.pid, identity=process_start_identity(child.pid), attempt=attempt)
            result['processes'].append(proc)
            try:
                deadline = time.monotonic() + 35
                while child.poll() is None:
                    marker = root / 'blocked.json'
                    if marker.exists() and not result['snapshots']:
                        active = read(root / 'active-process.json')
                        assert read(marker) == active
                        assert process_start_identity(active['pid']) == active['identity']
                        proc['worker'] = active
                        state = store.load_status(parent).to_dict()
                        assert state['state'] == 'running' and state['pid'] == active['pid']
                        locks = {str(p.relative_to(data)): read(p) for p in data.glob('jobs/**/owner.json')}
                        try:
                            with store.claim(parent, 'reading_pipeline'):
                                raise AssertionError('concurrent_claim_admitted')
                        except JobClaimUnavailable:
                            result['concurrent_claim_rejected'] = True
                        assert pipeline.start(paper).parent_job_id == parent
                        protected = assets(root)
                        result['snapshots'].append(dict(boundary=name, status=state, locks=locks, assets=protected))
                        os.kill(active['pid'], signal.SIGTERM)  # Registered task worker, identity checked above.
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError('worker_timeout')
                    time.sleep(.025)
                proc['exit'] = child.wait(timeout=8)
            finally:
                active_path = root / 'active-process.json'
                if active_path.exists():
                    active = read(active_path)
                    proc['worker'] = active
                    if store._pid_is_alive(active['pid']) and process_start_identity(active['pid']) == active['identity']:
                        os.kill(active['pid'], signal.SIGTERM)
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=8)
                proc['alive_after_wait'] = store._pid_is_alive(child.pid)
                proc['worker_alive_after_wait'] = store._pid_is_alive(proc['worker']['pid'])
        status = store.load_status(parent)
        state = read(store.handle(parent).reading_pipeline_path)
        result['attempts'].append(dict(status=status.to_dict(), pipeline=state, assets=assets(root)))
        if proc['exit'] == 1:
            break  # Preserve an unhandled reload failure; do not fabricate recovery.
        if status.state == 'running':
            # Recovery inspect is deliberately performed by the NEXT process.
            supplied = {}
            continue
        if status.state == 'completed':
            break
        if status.state == 'failed':
            if attempt > 0 and status.error not in {'controlled_parse_fail_before', 'controlled_translation_fail_after'}:
                break
            supplied = {}
            continue
        if status.state == 'waiting_agent':
            required = status.required_input
            if status.reason_code in {'translate_full_read', 'full_translation_revision_required'} and required.get('source_manifest_path'):
                supplied = {'full_translation': _translation(read(Path(required['source_manifest_path'])))}
            elif status.reason_code == 'review_full_read':
                supplied = {'full_review': _review(required)}
            else:
                break
        else:
            break
    try:
        final = pipeline.inspect(parent)
    except Exception as error:
        result['inspect_error'] = str(error)
        from scientific_reading.reading_pipeline_models import ReadingPipelineState
        final = ReadingPipelineState.from_dict(read(store.handle(parent).reading_pipeline_path))
    result['final'] = final.to_dict()
    result['final_assets'] = assets(root)
    result['protected_assets_unchanged'] = all(result['final_assets'].get(p) == digest for p, digest in protected.items())
    try:
        result['duplicate_start_id'] = pipeline.start(paper).parent_job_id
    except Exception as error:
        result['duplicate_start_error'] = str(error)
        result['duplicate_start_id'] = None
    if final.state == 'completed':
        before = assets(root)
        assert pipeline.advance(parent, {}).to_dict() == final.to_dict()
        assert assets(root) == before
    result['calls'] = [json.loads(line) for line in (root / 'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    library = LibraryService(data)
    try:
        result['library_item'] = library.get_item(paper)
        result['schema'] = library.conn.execute('PRAGMA user_version').fetchone()[0]
    finally:
        library.close()
    # Wait for every derived worker spawned by the REAL schedule adapter.
    result['derived'] = []
    for marker in data.glob('jobs/*/launch.json'):
        value = read(marker)
        deadline = time.monotonic() + 20
        while store._pid_is_alive(value['pid']) and time.monotonic() < deadline:
            time.sleep(.05)
        result['derived'].append(dict(marker=value, alive=store._pid_is_alive(value['pid']),
                                     status=store.load_status(marker.parent.name).to_dict()))
    result['live_owned_processes'] = [p for p in result['processes'] if p['alive_after_wait'] or p['worker_alive_after_wait']] + [p for p in result['derived'] if p['alive']]
    atomic_write_json(root / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    args.output.mkdir(parents=True, exist_ok=True)
    results = [scenario(args.output / name, name) for name in SCENARIOS]
    summary = [dict(scenario=r['scenario'], state=r['final']['state'], error=r['final']['last_error'],
                    protected=r['protected_assets_unchanged'], live=r['live_owned_processes']) for r in results]
    atomic_write_json(args.output / 'summary.json', summary)
    print(json.dumps(summary, indent=2))
    return int(any(r['final']['state'] != 'completed' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
