import importlib.util
from pathlib import Path
import tempfile

import pytest

spec = importlib.util.spec_from_file_location('control_process', Path(__file__).resolve().parents[2] / 'scripts/v02-004f-process.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('point', probe.SCENARIOS)
def test_real_provider_stop_boundary(point):
    with tempfile.TemporaryDirectory(prefix='v4f-') as root:
        result = probe.scenario(Path(root) / 'case', point)
    assert result['final']['state'] == 'completed'
    assert result['protected_assets_unchanged']
    assert not any(p['alive'] for p in result['processes'] + result['children'])

def test_cross_process_stop_start_and_resume_races(tmp_path):
    import json
    import subprocess
    import sys
    import time
    from scientific_reading.library_service import LibraryService
    from scientific_reading.models import PaperMetadata
    from scientific_reading.reading_pipeline import ReadingPipeline
    from scientific_reading.reading_control import ReadingControl
    library = LibraryService(tmp_path)
    paper = library.ingest(PaperMetadata(title='race only missing PDF', doi='10.5555/race'))['paper_id']
    library.close()
    pipeline = ReadingPipeline(tmp_path)
    parent = pipeline.start(paper).parent_job_id
    control = ReadingControl(pipeline.job_store, parent)

    def race(commands):
        children = [subprocess.Popen([sys.executable, '-m', 'scientific_reading', '--data-root', str(tmp_path), *args],
            env=probe.environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) for args in commands]
        outputs = []
        try:
            for child in children:
                out, err = child.communicate(timeout=40)
                outputs.append((child.returncode, json.loads(out)))
                assert not err, err
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
        deadline = time.monotonic() + 30
        for marker in (tmp_path / 'jobs').glob('*/launch.json'):
            pid = probe.read(marker)['pid']
            while pipeline.job_store._pid_is_alive(pid) and time.monotonic() < deadline:
                time.sleep(.05)
            assert not pipeline.job_store._pid_is_alive(pid)
        return outputs

    result = race([['full-read-pipeline-stop', '--job-id', parent, '--request-id', 's', '--expected-revision', '0'],
                   ['full-read-pipeline-start', '--paper-id', paper],
                   ['full-read-pipeline-stop', '--job-id', parent, '--request-id', 's', '--expected-revision', '0']])
    assert all(x[0] == 0 for x in result), result
    assert control.read()['status'] == 'acknowledged'
    before = control.store.handle(parent).reading_pipeline_path.read_bytes()
    result = race([['full-read-pipeline-stop', '--job-id', parent, '--request-id', 's2', '--expected-revision', '1'],
                   ['full-read-pipeline-resume', '--job-id', parent, '--resume-stopped', '--request-id', 'r', '--expected-revision', '1']])
    assert sorted(x[0] for x in result) == [0, 4], result
    assert [x for x in result if x[0] == 4][0][1]['error'] == 'reading_control_revision_conflict'
    assert control.read()['revision'] == 2
    if control.read()['stopRequested']:
        assert control.store.handle(parent).reading_pipeline_path.read_bytes() == before
    else:
        control.stop('s3', 2)
    result = race([['full-read-pipeline-resume', '--job-id', parent],
                   ['full-read-pipeline-start', '--paper-id', paper],
                   ['full-read-pipeline-stop', '--job-id', parent, '--request-id', 's', '--expected-revision', '0']])
    assert [x[0] for x in result] == [2, 0, 0]
    assert control.read()['stopRequested']
    revision = control.read()['revision']
    events_before = sum(e['state'] == 'running' for e in control.store.read_events(parent))
    command = ['full-read-pipeline-resume', '--job-id', parent, '--resume-stopped',
               '--request-id', 'explicit-final', '--expected-revision', str(revision)]
    result = race([command, command])
    assert [x[0] for x in result] == [0, 0], result
    assert control.read()['revision'] == revision + 1
    assert sum(e['state'] == 'running' for e in control.store.read_events(parent)) - events_before == 1
    control.stop('final-stop', revision + 1)
    result = race([command])
    assert result[0][0] == 0 and result[0][1]['stopRequested']
    assert control.read()['revision'] == revision + 2


def test_old_live_worker_without_capability_is_only_requested(tmp_path):
    import subprocess
    import sys
    import time
    from scientific_reading.library_service import LibraryService
    from scientific_reading.models import PaperMetadata
    from scientific_reading.reading_pipeline import ReadingPipeline
    from scientific_reading.reading_control import ReadingControl
    library = LibraryService(tmp_path)
    paper = library.ingest(PaperMetadata(title='legacy worker'))['paper_id']
    library.close()
    pipeline = ReadingPipeline(tmp_path)
    parent = pipeline.start(paper).parent_job_id
    marker = tmp_path / 'ready'
    release = tmp_path / 'release'
    # A real process using only the old background store transition contract;
    # intentionally has no control capability registration or boundary checks.
    code = '''import sys,time,os
from pathlib import Path
from scientific_reading.background_store import BackgroundJobStore
root=Path(sys.argv[1]);store=BackgroundJobStore(root);job=sys.argv[2]
store.transition(job,'running',pid=os.getpid());(root/'ready').touch()
while not (root/'release').exists():time.sleep(.02)
store.transition(job,'failed',error='legacy_finished_failure')
'''
    child = subprocess.Popen([sys.executable, '-c', code, str(tmp_path), parent], env=probe.environment(),
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists()
        control = ReadingControl(pipeline.job_store, parent)
        for index in range(2):
            reply = control.stop('legacy-stop', 0) if index == 0 else control.read()
            assert reply['status'] == 'requested'
            assert reply['acknowledgedRevision'] is None
        release.touch()
        assert child.wait(timeout=10) == 0
        reply = control.read()
        assert reply['status'] == 'terminal'
        assert reply['businessStatus']['error'] == 'legacy_finished_failure'
    finally:
        release.touch()
        if child.poll() is None:
            child.wait(timeout=10)
