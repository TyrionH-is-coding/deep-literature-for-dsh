import hashlib
import pytest

from scientific_reading.background_models import AgentRequired, UserActionRequired
from scientific_reading.library_service import LibraryService
from scientific_reading.reading_control import ReadingControl
from scientific_reading.reading_pipeline import ReadingPipeline
from scientific_reading.worker import run_job, full_read_pipeline_handler_factory


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def make_parent(root, metadata, outcome):
    library = LibraryService(root)
    try:
        paper = library.ingest(metadata)['paper_id']
    finally:
        library.close()
    def runner(*_):
        if outcome == 'failed':
            raise RuntimeError('controlled_failure')
        if outcome == 'waiting_user':
            raise UserActionRequired('controlled_user', {})
        raise AgentRequired('controlled_agent', {})
    pipeline = ReadingPipeline(root, stage_runner=runner)
    job = pipeline.start(paper).parent_job_id
    assert run_job(pipeline.job_store, job, {'full_read_pipeline': full_read_pipeline_handler_factory(pipeline)}) in (2, 3, 4)
    assert pipeline.job_store.load_status(job).state == outcome
    return pipeline, job


@pytest.mark.parametrize('outcome', ['failed', 'waiting_user', 'waiting_agent'])
@pytest.mark.parametrize('supplied', [{}, {'unexpected': True}])
@pytest.mark.parametrize('legacy', [False, True])
def test_explicit_terminal_advance_rejects_before_any_write(tmp_path, metadata, outcome, supplied, legacy):
    pipeline, job = make_parent(tmp_path, metadata, outcome)
    if legacy:
        ReadingControl(pipeline.job_store, job).path.unlink()
    before = snapshot(tmp_path)
    pipeline.stage_runner = lambda *_: pytest.fail('runner must not be entered')
    with pytest.raises(RuntimeError, match='^full_read_pipeline_resume_required$'):
        pipeline.advance(job, supplied)
    assert snapshot(tmp_path) == before
    assert pipeline.inspect(job).state == {'waiting_user': 'needs_user'}.get(outcome, outcome)


@pytest.mark.parametrize('outcome', ['failed', 'waiting_user', 'waiting_agent'])
def test_none_does_not_resume(tmp_path, metadata, outcome):
    pipeline, job = make_parent(tmp_path, metadata, outcome)
    before = snapshot(tmp_path)
    pipeline.stage_runner = lambda *_: pytest.fail('no automatic recovery')
    state = pipeline.advance(job)
    assert state.state == {'waiting_user': 'needs_user'}.get(outcome, outcome)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('background', ['queued', 'running'])
@pytest.mark.parametrize('outcome', ['failed', 'waiting_user', 'waiting_agent'])
def test_requeued_lifecycle_allows_explicit_single_step(tmp_path, metadata, background, outcome):
    pipeline, job = make_parent(tmp_path, metadata, outcome)
    pipeline.job_store.transition(job, 'queued')
    if background == 'running':
        pipeline.job_store.transition(job, 'running')
    calls = []
    def runner(stage, state, supplied):
        calls.append((stage, supplied))
        return {'status': 'pdf_ready', 'source_pdf_sha256': 'a' * 64}
    pipeline.stage_runner = runner
    result = pipeline.advance(job, {})
    assert calls == [('ensure_pdf', {})]
    assert result.current_stage == 'parse_mineru'
    assert pipeline.inspect(job).state == 'queued'
    assert pipeline.job_store.load_status(job).state == background


def test_completed_is_idempotent(tmp_path, metadata):
    pipeline, job = make_parent(tmp_path, metadata, 'failed')
    pipeline.job_store.transition(job, 'queued')
    state = pipeline._load(job)
    pipeline._complete(state)
    pipeline.job_store.transition(job, 'running')
    pipeline.job_store.transition(job, 'completed')
    before = snapshot(pipeline.job_store.handle(job).root)
    pipeline.stage_runner = lambda *_: pytest.fail('completed must not run')
    assert pipeline.advance(job, {}).state == 'completed'
    assert snapshot(pipeline.job_store.handle(job).root) == before
    assert pipeline.inspect(job).state == 'completed'


@pytest.mark.parametrize('outcome', ['waiting_user', 'waiting_agent'])
def test_stop_gate_precedes_lifecycle_rejection(tmp_path, metadata, outcome):
    pipeline, job = make_parent(tmp_path, metadata, outcome)
    control = ReadingControl(pipeline.job_store, job)
    control.stop('stop', 0)
    before = snapshot(tmp_path)
    result = pipeline.advance(job, {})
    assert result.required_action['reason_code'] == 'pipeline_stop_requested'
    assert control.load()['stopRequested']
    assert snapshot(tmp_path) == before
