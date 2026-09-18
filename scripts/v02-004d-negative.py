"""Bounded legacy running-checkpoint exception and unchanged commit guards."""
import importlib.util
from pathlib import Path
import tempfile

# Standalone assertion adapter; no third-party package or production import overlay.
import re
from contextlib import contextmanager
from types import SimpleNamespace
class AssertionAdapter:
    fixture = staticmethod(lambda fn: fn)
    mark = SimpleNamespace(parametrize=lambda *args: (lambda fn: fn))
    @staticmethod
    @contextmanager
    def raises(kind, match=None):
        caught = SimpleNamespace(value=None)
        try:
            yield caught
        except kind as error:
            caught.value = error
            if match is not None:
                assert re.search(match, str(error)), str(error)
        else:
            raise AssertionError('expected ' + str(kind))
pytest = AssertionAdapter()


from scientific_reading.models import StageRecord

spec = importlib.util.spec_from_file_location('recovery_probe', Path(__file__).with_name('v02-004d-probe.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.fixture
def pending():
    with tempfile.TemporaryDirectory(prefix='v4b-') as directory:
        root = Path(directory)
        p.atomic_write_json(root / 'config.json', {'scenario': 'baseline'})
        data = root / 'data'
        library = p.LibraryService(data)
        try:
            paper = library.ingest(p._metadata())['paper_id']
        finally:
            library.close()
        base = p.PaperWorkspace.create_for_paper_id(data, paper, p._metadata())
        p._fixture_pdf(base.source_pdf)
        pipeline = p.ReadingPipeline(data, mineru_service=p.Parse(root))
        parent = pipeline.start(paper).parent_job_id
        state = pipeline.advance(parent)
        digest = state.source_pdf_sha256
        generation = pipeline._stage_workspace(base, p._metadata(), digest, 'paper_parse_upgrade')
        job = generation.load_job()
        job.status = 'mineru_running'
        job.stages['paper_parse_upgrade'] = StageRecord(status='running', result={'method': 'auto'})
        generation.save_job(job)
        yield pipeline, base, generation, digest, parent, root


@pytest.mark.parametrize('with_sha', [False, True])
def test_same_source_running_checkpoint_retries(pending, with_sha):
    pipeline, base, generation, digest, parent, root = pending
    job = generation.load_job()
    if with_sha:
        job.stages['paper_parse_upgrade'].result['source_sha256'] = digest
        generation.save_job(job)
    assert pipeline._stage_workspace(base, p._metadata(), digest, 'paper_parse_upgrade').root == generation.root
    assert pipeline.advance(parent).current_stage == 'translate_full'
    assert generation.load_job().stages['paper_parse_upgrade'].status == 'completed'


@pytest.mark.parametrize('mutation', [
    'explicit_other_sha', 'explicit_null_sha', 'completed_missing_sha', 'completed_other_sha',
    'failed', 'queued', 'wrong_job_status', 'pdf_unconfirmed', 'pdf_hash_missing',
    'pdf_hash_other', 'missing_generation_source', 'changed_generation_source',
    'changed_base_source', 'metadata', 'directory_identity', 'published_target', 'published_manifest', 'other_stage',
])
def test_legacy_exception_rejects_conflicts(pending, mutation):
    pipeline, base, generation, digest, _, _ = pending
    job = generation.load_job()
    stage = job.stages['paper_parse_upgrade']
    pointer_stage = 'paper_parse_upgrade'
    if mutation == 'explicit_other_sha': stage.result['source_sha256'] = digest[:16] + '0' * 48
    elif mutation == 'explicit_null_sha': stage.result['source_sha256'] = None
    elif mutation.startswith('completed_'):
        stage.status = 'completed'
        if mutation.endswith('other_sha'): stage.result['source_sha256'] = '0' * 64
    elif mutation in {'failed', 'queued'}: stage.status = mutation
    elif mutation == 'wrong_job_status': job.status = 'pdf_ready'
    elif mutation == 'pdf_unconfirmed': job.stages['pdf_acquisition'].status = 'running'
    elif mutation == 'pdf_hash_missing': job.stages['pdf_acquisition'].result.pop('sha256')
    elif mutation == 'pdf_hash_other': job.stages['pdf_acquisition'].result['sha256'] = '0' * 64
    elif mutation == 'missing_generation_source': generation.source_pdf.unlink()
    elif mutation == 'changed_generation_source': generation.source_pdf.write_bytes(b'changed')
    elif mutation == 'changed_base_source': base.source_pdf.write_bytes(b'changed')
    elif mutation == 'metadata':
        metadata = p.read(generation.metadata_path)
        metadata['doi'] = '10.9999/conflict'
        p.atomic_write_json(generation.metadata_path, metadata)
    elif mutation == 'published_target': (generation.parsed_dir / 'mineru').mkdir()
    elif mutation == 'published_manifest': p.atomic_write_json(generation.manifest_path, {'version': 1, 'assets': []})
    elif mutation == 'other_stage':
        pointer_stage = 'paper_parse'
        job.stages[pointer_stage] = stage
    generation.save_job(job)
    if mutation == 'directory_identity':
        payload = p.read(generation.job_path)
        payload['paper_id'] = 'wrong-generation'
        p.atomic_write_json(generation.job_path, payload)
    for _ in range(2):
        with pytest.raises(ValueError, match='generation_(workspace|source)_conflict'):
            pipeline._stage_workspace(base, p._metadata(), digest, pointer_stage)


@pytest.mark.parametrize('with_sha', [False, True])
def test_running_never_satisfies_require_stage(pending, with_sha):
    pipeline, base, generation, digest, _, _ = pending
    job = generation.load_job()
    if with_sha:
        job.stages['paper_parse_upgrade'].result['source_sha256'] = digest
    generation.save_job(job)
    base_job = base.load_job()
    base_job.stages['paper_parse_upgrade'] = StageRecord(status='completed', result={
        'source_sha256': digest, 'active_workspace': f'generations/{digest[:16]}'})
    base.save_job(base_job)
    with pytest.raises(ValueError, match='generation_workspace_conflict'):
        pipeline._stage_workspace(base, p._metadata(), digest, 'paper_parse_upgrade', require_stage=True)


def test_confirmed_cache_corruption_never_calls_provider(pending):
    pipeline, base, generation, digest, parent, root = pending
    assert pipeline.advance(parent).current_stage == 'translate_full'
    target = generation.parsed_dir / 'mineru/full.md'
    target.write_text('damaged confirmed output', encoding='utf-8')
    before = (root / 'calls.jsonl').read_bytes()
    with pytest.raises(Exception, match='mineru_artifact_inconsistent'):
        p.Parse(root).run(root / 'data', p._metadata(), 'auto', heartbeat=lambda: None,
                          paper_id=base.root.name, workspace=generation, upgrade_reason='full-read')
    assert (root / 'calls.jsonl').read_bytes() == before
    assert target.read_text(encoding='utf-8') == 'damaged confirmed output'
