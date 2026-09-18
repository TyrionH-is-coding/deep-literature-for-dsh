import json
import os
from types import SimpleNamespace

import pytest

from scientific_reading.__main__ import _validate_full_read_resume, run_cli
from scientific_reading.background_launcher import BackgroundLauncher
from scientific_reading.library_service import LibraryService
from scientific_reading.models import PaperMetadata
from scientific_reading.reading_control import ReadingControl, ReadingControlError
from scientific_reading.reading_pipeline import ReadingPipeline
from scientific_reading.scope import use_scope
from scientific_reading.worker import run_job, full_read_pipeline_handler_factory
from scientific_reading.workspace import atomic_write_json


@pytest.fixture
def parent(tmp_path, metadata):
    library = LibraryService(tmp_path)
    paper = library.ingest(metadata)['paper_id']
    library.close()
    pipeline = ReadingPipeline(tmp_path, stage_runner=lambda *_: {})
    job = pipeline.start(paper).parent_job_id
    return pipeline, ReadingControl(pipeline.job_store, job), paper


class Launch:
    def __init__(self):
        self.calls = []

    def launch_existing(self, job):
        self.calls.append(job)


def resume(control, launcher, key='resume', revision=1, supplied=None):
    return control.resume(key, revision, supplied or {}, validate=_validate_full_read_resume, launcher=launcher)


def test_stop_replay_revision_and_resume_receipt_loss(parent):
    pipeline, control, paper = parent
    original = control.store.handle(control.job_id).reading_pipeline_path.read_bytes()
    assert control.read()['revision'] == 0
    assert not control.path.exists()
    assert control.stop('stop', 0)['status'] == 'acknowledged'
    assert control.stop('stop', 0)['revision'] == 1
    assert control.store.handle(control.job_id).reading_pipeline_path.read_bytes() == original
    assert pipeline.advance(control.job_id, {}).required_action['reason_code'] == 'pipeline_stop_requested'
    assert pipeline.start(paper).state == 'needs_user'
    assert not BackgroundLauncher(pipeline.data_root, popen=lambda *_: pytest.fail('spawn')).launch_existing(control.job_id).process_started
    assert run_job(control.store, control.job_id) == 2
    with pytest.raises(ReadingControlError, match='revision_conflict'):
        control.stop('stale', 0)
    with pytest.raises(ReadingControlError, match='request_conflict'):
        control.stop('stop', 1)
    launched = Launch()
    assert resume(control, launched)['revision'] == 2
    assert resume(control, launched)['revision'] == 2
    assert launched.calls == [control.job_id]
    assert control.stop('stop2', 2)['revision'] == 3
    assert resume(control, launched)['stopRequested']
    assert control.stop('stop', 0)['revision'] == 3
    assert launched.calls == [control.job_id]
    with pytest.raises(ReadingControlError, match='request_conflict'):
        resume(control, launched, key='stop', revision=0)


@pytest.mark.parametrize('damage', ['json', 'contract', 'operations', 'ack', 'active', 'revision'])
def test_corrupt_control_fails_closed(parent, damage):
    pipeline, control, paper = parent
    value = control.load()
    if damage == 'json':
        control.path.write_text('{', encoding='utf-8')
    else:
        if damage == 'contract': value['contract'] = 'future'
        if damage == 'operations': value['operations'] = {'bad': {}}
        if damage == 'ack': value['acknowledgedRevision'] = 1
        if damage == 'active': value['activeStage'] = {'pid': 'oops'}
        if damage == 'revision': value['revision'] = True
        atomic_write_json(control.path, value)
    before = control.path.read_bytes()
    for action in [control.read, lambda: control.stop('stop', 0), lambda: pipeline.advance(control.job_id),
                   lambda: pipeline.start(paper), lambda: BackgroundLauncher(pipeline.data_root).launch_existing(control.job_id),
                   lambda: resume(control, Launch())]:
        with pytest.raises(ReadingControlError, match='reading_control_invalid'):
            action()
        assert control.path.read_bytes() == before


def test_unknown_worker_and_terminal_priority(parent):
    pipeline, control, paper = parent
    control.store.transition(control.job_id, 'running', pid=os.getpid())
    assert control.stop('stop', 0)['status'] == 'requested'
    assert control.read()['acknowledgedRevision'] is None
    with pytest.raises(ReadingControlError, match='stop_unconfirmed'):
        resume(control, Launch())
    control.store.transition(control.job_id, 'failed', error='actual failure')
    assert control.read()['status'] == 'terminal'
    assert control.read()['businessStatus']['error'] == 'actual failure'


def test_gate_preserved_and_resume_must_validate_it(parent):
    pipeline, control, paper = parent
    from scientific_reading.background_models import AgentRequired
    def gate(*_):
        raise AgentRequired('translate_full_read', {})
    pipeline.stage_runner = gate
    assert run_job(control.store, control.job_id, {'full_read_pipeline': full_read_pipeline_handler_factory(pipeline)}) == 3
    state = control.store.handle(control.job_id).reading_pipeline_path.read_bytes()
    control.stop('stop', 0)
    before = control.path.read_bytes()
    with pytest.raises(ValueError, match='full_translation_resume_input_invalid'):
        resume(control, Launch())
    assert control.path.read_bytes() == before
    assert control.store.handle(control.job_id).reading_pipeline_path.read_bytes() == state


def test_pending_resume_dispatch_is_reconciled(parent):
    pipeline, control, paper = parent
    control.stop('stop', 0)
    class Lost:
        def launch_existing(self, job):
            raise OSError('lost before spawn')
    with pytest.raises(OSError):
        resume(control, Lost())
    assert control.read()['revision'] == 2
    launched = Launch()
    resume(control, launched)
    resume(control, launched)
    assert launched.calls == [control.job_id]


def test_cli_json_gate_and_scope_isolation(tmp_path, capsys):
    library = LibraryService(tmp_path)
    folder = library.create_folder('first')['folder_id']
    other = library.create_folder('second')['folder_id']
    paper = library.ingest(PaperMetadata(title='first', doi='10.5555/first'))['paper_id']
    second = library.ingest(PaperMetadata(title='second', doi='10.5555/second'))['paper_id']
    library.move_items([paper, second], folder)
    scope = dict(instanceId='test', scopeSessionId='session', scopeFolderId=folder)
    with use_scope(scope):
        pipeline = ReadingPipeline(tmp_path)
        job = pipeline.start(paper).parent_job_id
        other_job = pipeline.start(second).parent_job_id
        def cli(command, *args):
            code = run_cli(['--data-root', str(tmp_path), command, '--job-id', job, *args])
            return code, json.loads(capsys.readouterr().out)
        assert cli('full-read-pipeline-stop', '--request-id', 's', '--expected-revision', '0')[0] == 0
        assert cli('full-read-pipeline-resume')[0] == 2
        code, value = cli('full-read-pipeline-control')
        assert code == 0 and value['stopRequested']
        assert ReadingControl(pipeline.job_store, other_job).read()['revision'] == 0
    with use_scope({**scope, 'scopePaperId': second}):
        assert cli('full-read-pipeline-control')[0] == 4
        assert cli('full-read-pipeline-stop', '--request-id', 'forbidden', '--expected-revision', '1')[0] == 4
    library.move_items([paper], other)
    with use_scope(scope):
        assert cli('full-read-pipeline-resume', '--resume-stopped', '--request-id', 'r', '--expected-revision', '1')[0] == 4
    assert ReadingControl(pipeline.job_store, job).read()['revision'] == 1
    library.close()

def test_attach_identity_and_generic_resume_cannot_bypass_stop(parent, capsys, tmp_path):
    from scientific_reading.__main__ import resume_job
    pipeline, control, paper = parent
    control.stop('stop', 0)
    with pytest.raises(ValueError, match='pipeline_stop_requested'):
        resume_job(control.store, control.job_id, launcher=Launch())
    pdf = tmp_path / 'unused.pdf'
    pdf.write_bytes(b'%PDF-1.4\n')
    base = ['--data-root', str(tmp_path), 'full-read-pdf-attach-resume', '--job-id', control.job_id, '--pdf', str(pdf)]
    assert run_cli([*base, '--paper-id', 'different']) == 4
    assert json.loads(capsys.readouterr().out)['error'] == 'full_read_parent_mismatch'
    assert run_cli([*base, '--paper-id', paper]) == 2
    assert json.loads(capsys.readouterr().out)['stopRequested']
    assert not (tmp_path / 'papers' / paper / 'source.pdf').exists()


def test_source_change_rejects_resume_without_revision_side_effect(parent, metadata):
    from scientific_reading.workspace import PaperWorkspace
    import hashlib
    pipeline, control, paper = parent
    workspace = PaperWorkspace.create_for_paper_id(pipeline.data_root, paper, metadata)
    workspace.source_pdf.write_bytes(b'%PDF-1.4\noriginal')
    sha = hashlib.sha256(workspace.source_pdf.read_bytes()).hexdigest()
    pipeline.stage_runner = lambda *_: {'source_pdf_sha256': sha}
    pipeline.advance(control.job_id)
    control.stop('stop', 0)
    before = control.path.read_bytes()
    workspace.source_pdf.write_bytes(b'%PDF-1.4\nchanged')
    with pytest.raises(ReadingControlError, match='full_read_parent_mismatch'):
        resume(control, Launch())
    assert control.path.read_bytes() == before


def test_control_command_refuses_mismatched_pipeline_identity(parent):
    pipeline, control, paper = parent
    path = control.store.handle(control.job_id).reading_pipeline_path
    value = json.loads(path.read_text(encoding='utf-8'))
    value['paper_id'] = 'other_paper'
    atomic_write_json(path, value)
    with pytest.raises(ReadingControlError, match='full_read_parent_mismatch'):
        control.stop('stop', 0)
    assert not control.path.exists()

@pytest.mark.parametrize('pid', [42424242, None])
def test_pending_resume_never_relaunches_recorded_attempt(parent, pid):
    pipeline, control, paper = parent
    control.stop('s', 0)
    class ReceiptLost:
        def launch_existing(self, job):
            atomic_write_json(control.path.parent / 'launch.json', {'controlRevision': 2, 'pid': pid})
            raise OSError('receipt_lost_after_launch_record')
    with pytest.raises(OSError):
        resume(control, ReceiptLost())
    launched = Launch()
    if pid is None:
        with pytest.raises(ReadingControlError, match='dispatch_uncertain'):
            resume(control, launched)
    else:
        assert resume(control, launched)['revision'] == 2
    assert launched.calls == []
