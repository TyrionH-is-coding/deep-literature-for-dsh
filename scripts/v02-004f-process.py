"""004F synthetic real-process boundary evidence; only provider/input are fixtures."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'engine/src'), str(REPO / 'engine'), str(REPO / 'scripts')]
spec = importlib.util.spec_from_file_location('prior_fixture', REPO / 'scripts/v02-004a-probe.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
from scientific_reading.reading_control import ReadingControl
from scientific_reading.__main__ import _validate_full_read_resume
from scientific_reading.background_launcher import process_start_identity

read, atomic_write_json = prior.read, prior.atomic_write_json
SCENARIOS = ('parse', 'batch', 'before_reader', 'reader', 'derived')


def environment():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('SR_SCOPE', 'MINERU_', 'FEISHU_', 'SR_SCANSCI', 'SCANSCI_')):
            env.pop(key)
    env.update(PYTHONPATH=os.pathsep.join([str(REPO / 'engine/src'), str(REPO / 'engine')]),
               PYTHONDONTWRITEBYTECODE='1', SR_NATIVE_KEYRING_TEST='0', PYTHONUTF8='1')
    return env


def hold(root, point):
    config = read(root / 'config.json')
    if config['scenario'] != point or (root / 'held.json').exists():
        return
    atomic_write_json(root / 'held.json', dict(point=point, pid=os.getpid(), identity=process_start_identity(os.getpid())))
    deadline = time.monotonic() + 90
    while not (root / 'release').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('controlled_provider_release_timeout')
        time.sleep(.02)


class Provider(prior.Provider):
    def parse(self, *args):
        hold(self.root, 'parse')
        return super().parse(*args)


class Full(prior.FullReadService):
    def __init__(self, root):
        super().__init__()
        self.root = root

    def save_translation_batch(self, *args):
        path = super().save_translation_batch(*args)
        prior.event(self.root, 'batch_committed', sha=prior.sha(path))
        hold(self.root, 'batch')
        return path


def worker(root):
    def forbidden(*_a, **_kw):
        raise AssertionError('004f_network_forbidden')
    socket.socket.connect = forbidden
    socket.create_connection = forbidden
    config = read(root / 'config.json')
    parse = prior.MineruParseService(provider_factory=lambda *_: Provider(root))
    pipeline = prior.ReadingPipeline(root / 'data', mineru_service=parse, full_read_service=Full(root))
    original = pipeline.stage_runner
    def runner(stage, state, supplied):
        prior.event(root, 'stage_enter', stage=stage)
        output = original(stage, state, supplied)
        prior.event(root, 'stage_committed', stage=stage)
        if stage == 'translate_full': hold(root, 'before_reader')
        if stage == 'render_reader': hold(root, 'reader')
        if stage == 'schedule_derived_updates': hold(root, 'derived')
        return output
    pipeline.stage_runner = runner
    return prior.run_job(pipeline.job_store, config['parent'], {'full_read_pipeline':
        prior.full_read_pipeline_handler_factory(pipeline, pipeline_input=read(root / 'input.json'))})


def cli(root, command, *extra):
    config = read(root / 'config.json')
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'scientific_reading', '--data-root', str(root / 'data'),
        command, '--job-id', config['parent'], *extra], env=environment(), capture_output=True, text=True,
        encoding='utf-8', timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    value = json.loads(result.stdout)
    prior.event(root, 'cli', command=command, args=extra, code=result.returncode, result=value)
    return result.returncode, value


def inputs(status):
    if status.reason_code in {'translate_full_read', 'full_translation_revision_required'}:
        return {'full_translation': prior._translation(read(Path(status.required_input['source_manifest_path'])))}
    if status.reason_code == 'review_full_read':
        return {'full_review': prior._review(status.required_input)}
    return {}


class QueueOnly:
    def launch_existing(self, job):
        pass  # The test launches the controlled provider worker as a real child next.


def reader_pointer(data, paper):
    library = prior.LibraryService(data)
    try:
        return [list(row) for row in library.conn.execute(
            "SELECT rel_path,status,updated_at FROM artifacts WHERE paper_id=? AND kind='reader'", (paper,)).fetchall()]
    finally:
        library.close()


def scenario(root, point):
    root.mkdir(parents=True, exist_ok=False)
    data = root / 'data'
    library = prior.LibraryService(data)
    paper = library.ingest(prior._metadata())['paper_id']
    library.close()
    workspace = prior.PaperWorkspace.create_for_paper_id(data, paper, prior._metadata())
    prior._fixture_pdf(workspace.source_pdf)
    pipeline = prior.ReadingPipeline(data)
    parent = pipeline.start(paper).parent_job_id
    store = pipeline.job_store
    control = ReadingControl(store, parent)
    atomic_write_json(root / 'config.json', dict(scenario=point, parent=parent))
    supplied = None
    results = dict(scenario=point, parent=parent, processes=[], snapshots=[])
    stopped = False
    protected = {}
    for attempt in range(14):
        atomic_write_json(root / 'input.json', supplied)
        with (root / f'worker-{attempt}.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--worker', str(root)],
                env=environment(), stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                deadline = time.monotonic() + 45
                while child.poll() is None:
                    if (root / 'held.json').exists() and not stopped:
                        stopped = True
                        protected = prior.assets(root)
                        begin = time.monotonic()
                        code, requested = cli(root, 'full-read-pipeline-stop', '--request-id', 'stop', '--expected-revision', '0')
                        assert code == 0 and requested['status'] == 'requested', requested
                        assert requested['acknowledgedRevision'] is None
                        results['request_seconds'] = time.monotonic() - begin
                        assert results['request_seconds'] < 10
                        assert child.poll() is None
                        assert cli(root, 'full-read-pipeline-control')[1]['status'] == 'requested'
                        assert cli(root, 'full-read-pipeline-resume')[0] == 2
                        assert cli(root, 'full-read-pipeline-resume', '--resume-stopped', '--request-id', 'early', '--expected-revision', '1')[0] == 4
                        results['snapshots'].append(requested)
                        (root / 'release').touch()
                    if time.monotonic() > deadline:
                        raise TimeoutError('worker_timeout')
                    time.sleep(.025)
                code = child.wait(timeout=8)
            finally:
                (root / 'release').touch() if stopped else None
                if child.poll() is None:
                    child.terminate()  # Failure cleanup only; not the stop implementation.
                    child.wait(timeout=8)
            results['processes'].append(dict(pid=child.pid, code=code, alive=store._pid_is_alive(child.pid)))
        assert code in (0, 2, 3), (code, (root / f'worker-{attempt}.log').read_text(encoding='utf-8'))
        status = store.load_status(parent)
        if stopped:
            confirmed = cli(root, 'full-read-pipeline-control')[1]
            assert confirmed['status'] == ('terminal' if point == 'derived' else 'acknowledged'), confirmed
            assert all(prior.assets(root).get(k) == v for k, v in protected.items())
            pointer_before = reader_pointer(data, paper)
            results['reader_pointer_at_stop'] = pointer_before
            state_before = store.handle(parent).reading_pipeline_path.read_bytes()
            calls_before = [x for x in (root / 'calls.jsonl').read_text(encoding='utf-8').splitlines() if 'stage_enter' in x]
            # Two fresh CLI processes reload durable control. Ordinary resume/start/advance cannot clear it.
            for restart in range(2):
                assert cli(root, 'full-read-pipeline-control')[1]['stopRequested']
                assert cli(root, 'full-read-pipeline-stop', '--request-id', 'stop', '--expected-revision', '0')[1]['revision'] == 1
                assert pipeline.start(paper).parent_job_id == parent
                pipeline.advance(parent, {})
                from scientific_reading.background_launcher import BackgroundLauncher
                assert not BackgroundLauncher(data).launch_existing(parent).process_started
            assert store.handle(parent).reading_pipeline_path.read_bytes() == state_before
            assert reader_pointer(data, paper) == pointer_before
            assert calls_before == [x for x in (root / 'calls.jsonl').read_text(encoding='utf-8').splitlines() if 'stage_enter' in x]
            results['confirmed'] = confirmed
            results['protected_assets_unchanged'] = True
            stage = read(store.handle(parent).reading_pipeline_path)['current_stage']
            assert stage == dict(parse='translate_full', batch='translate_full', before_reader='render_reader', reader='schedule_derived_updates', derived='completed')[point]
            children = [p for p in (data / 'jobs').iterdir() if p.name != parent and p.is_dir()]
            assert bool(children) == (point == 'derived')
            results['child_count_at_stop'] = len(children)
            if point != 'derived':
                raw = read(store.handle(parent).reading_pipeline_path)
                raw_action = raw.get('required_action') or {}
                from types import SimpleNamespace
                supplied = inputs(SimpleNamespace(reason_code=raw_action.get('reason_code'), required_input=raw_action))
                resumed = control.resume('resume', 1, supplied, validate=_validate_full_read_resume, launcher=QueueOnly())
                assert resumed['revision'] == 2 and resumed['parentJobId'] == parent
                assert control.resume('resume', 1, supplied, validate=_validate_full_read_resume, launcher=QueueOnly())['revision'] == 2
            break
        if status.state == 'completed':
            raise AssertionError('boundary_not_observed')
        supplied = inputs(status)
        store.save_resume_input(parent, supplied)
        store.transition(parent, 'queued')
    assert stopped
    # Resume the same parent through remaining real stages, preserving all committed assets.
    if point != 'derived':
        for attempt2 in range(14):
            atomic_write_json(root / 'input.json', supplied)
            with (root / f'resume-{attempt2}.log').open('w', encoding='utf-8') as log:
                child = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--worker', str(root)],
                    env=environment(), stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                try:
                    code = child.wait(timeout=40)
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=8)
                results['processes'].append(dict(pid=child.pid, code=code, alive=store._pid_is_alive(child.pid)))
            assert code in (0, 3), (root / f'resume-{attempt2}.log').read_text(encoding='utf-8')
            status = store.load_status(parent)
            if status.state == 'completed': break
            supplied = inputs(status)
            store.save_resume_input(parent, supplied)
            store.transition(parent, 'queued')
    assert store.load_status(parent).state == 'completed'
    assert all(prior.assets(root).get(k) == v for k, v in protected.items())
    if results['reader_pointer_at_stop']:
        assert reader_pointer(data, paper) == results['reader_pointer_at_stop']
    results['final_reader_pointer'] = reader_pointer(data, paper)
    results['final'] = pipeline.inspect(parent).to_dict()
    results['assets'] = prior.assets(root)
    results['children'] = []
    for marker in data.glob('jobs/*/launch.json'):
        entry = read(marker)
        deadline = time.monotonic() + 25
        while store._pid_is_alive(entry['pid']) and time.monotonic() < deadline:
            time.sleep(.05)
        results['children'].append(dict(pid=entry['pid'], alive=store._pid_is_alive(entry['pid']), status=store.load_status(marker.parent.name).to_dict()))
    assert not any(p['alive'] for p in results['children'] + results['processes'])
    atomic_write_json(root / 'result.json', results)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.worker: raise SystemExit(worker(args.worker))
    args.output.mkdir(parents=True, exist_ok=True)
    summary = [scenario(args.output / point, point) for point in SCENARIOS]
    atomic_write_json(args.output / 'summary.json', summary)
    print(json.dumps([dict(scenario=x['scenario'], state=x['final']['state'], processes=x['processes'], children=x['children']) for x in summary], indent=2))
