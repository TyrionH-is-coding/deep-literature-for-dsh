"""V02-004A diagnostics: desired recovery assertions deliberately remain strict."""
import importlib.util
import json
from pathlib import Path
import tempfile

import pytest

spec = importlib.util.spec_from_file_location('v02_004a', Path(__file__).resolve().parents[2] / 'scripts/v02-004a-probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def short_root():
    # Deep production generation paths need a short Windows temp root.
    with tempfile.TemporaryDirectory(prefix='v4at-') as root:
        yield Path(root)


@pytest.mark.parametrize('boundary', probe.SCENARIOS)
def test_cross_process_stage_recovery(short_root, boundary):
    result = probe.scenario(short_root / 'case', boundary)
    assert not result['live_owned_processes']
    assert result['duplicate_start_id'] == result['parent']
    assert result['protected_assets_unchanged']
    assert result['final']['state'] == 'completed', result['final']
    assert result['schema'] == 4
    parses = [c for c in result['calls'] if c['name'] == 'provider_parse']
    assert len(parses) == (2 if boundary.endswith('before') else 1)
    saves = [c for c in result['calls'] if c['name'] == 'translation_save']
    assert len({c['batch'] for c in saves}) == len(saves)
    if '-kill-' in boundary:
        assert result['concurrent_claim_rejected']
        old = result['snapshots'][0]['status']['pid']
        recovered = [c for c in result['calls'] if c['name'] == 'worker_loaded' and c['before']['pid'] == old]
        assert len(recovered) == 1
        assert recovered[0]['pid'] != old
        assert recovered[0]['after']['state'] == 'queued'


def test_duplicate_translation_and_incomplete_candidate_are_non_destructive(short_root):
    root = short_root
    probe.atomic_write_json(root / 'config.json', {'scenario': 'baseline'})
    data = root / 'data'
    library = probe.LibraryService(data)
    try:
        paper = library.ingest(probe._metadata())['paper_id']
    finally:
        library.close()
    base = probe.PaperWorkspace.create_for_paper_id(data, paper, probe._metadata())
    probe._fixture_pdf(base.source_pdf)
    pipeline = probe.ReadingPipeline(data, mineru_service=probe.Parse(root))
    parent = pipeline.start(paper).parent_job_id
    pipeline.advance(parent)
    pipeline.advance(parent)
    gate = pipeline.advance(parent)
    assert gate.state == 'waiting_agent'
    source = probe.read(Path(gate.required_action['source_manifest_path']))
    generation = probe.PaperWorkspace(base.root / 'generations' / gate.source_pdf_sha256[:16])
    service = probe.FullReadService()
    submission = probe._translation(source)
    target = service.save_translation_batch(generation, submission)
    confirmed = target.read_bytes(), target.stat().st_mtime_ns
    assert service.save_translation_batch(generation, submission) == target
    assert (target.read_bytes(), target.stat().st_mtime_ns) == confirmed
    changed = json.loads(json.dumps(submission))
    changed['translations'][0]['translation_zh'] = 'Different candidate'
    with pytest.raises(Exception, match='translation_batch_conflict'):
        service.save_translation_batch(generation, changed)
    assert (target.read_bytes(), target.stat().st_mtime_ns) == confirmed
    # A partial new plan/review must not publish a Reader or change library pointer.
    invalid = pipeline.advance(parent, {'full_review': {}})
    assert invalid.state == 'waiting_agent'
    assert not generation.reader_html.exists()
    assert target.read_bytes() == confirmed[0]
    library = probe.LibraryService(data)
    try:
        assert library.conn.execute("SELECT count(*) FROM artifacts WHERE paper_id=? AND kind='reader'", (paper,)).fetchone()[0] == 0
    finally:
        library.close()


def test_engine_has_no_cancel_state_or_cli_command():
    from scientific_reading.background_store import ALLOWED_TRANSITIONS
    from scientific_reading.__main__ import _build_parser
    assert 'canceled' not in ALLOWED_TRANSITIONS
    # This is an explicit boundary assertion, NOT evidence that cancellation works.
    with pytest.raises(SystemExit) as caught:
        _build_parser().parse_args(['full-read-pipeline-cancel', '--job-id', 'job_0123456789abcdef'])
    assert caught.value.code == 2


def test_incomplete_new_generation_preserves_published_reader(short_root):
    result = probe.scenario(short_root / 'case', 'baseline')
    assert result['final']['state'] == 'completed'
    root = Path(result['root'])
    data = root / 'data'
    paper = result['final']['paper_id']
    library = probe.LibraryService(data)
    try:
        old_artifact = tuple(library.conn.execute(
            "SELECT rel_path, status, updated_at FROM artifacts WHERE paper_id=? AND kind='reader'", (paper,)).fetchone())
    finally:
        library.close()
    base = probe.PaperWorkspace.create_for_paper_id(data, paper, probe._metadata())
    old_reader = base.root / old_artifact[0]
    confirmed = old_reader.read_bytes(), old_reader.stat().st_mtime_ns
    pipeline = probe.ReadingPipeline(data, mineru_service=probe.Parse(root))
    # Repeated completed resume/start must not republish or rewrite formal Reader.
    pipeline.advance(result['parent'], {})
    assert pipeline.start(paper).parent_job_id == result['parent']
    library = probe.LibraryService(data)
    try:
        assert tuple(library.conn.execute(
            "SELECT rel_path, status, updated_at FROM artifacts WHERE paper_id=? AND kind='reader'", (paper,)).fetchone()) == old_artifact
    finally:
        library.close()
    base.source_pdf.write_bytes(base.source_pdf.read_bytes() + b'\n% changed synthetic source\n')
    new = pipeline.start(paper)
    assert new.parent_job_id != result['parent']
    pipeline.advance(new.parent_job_id)
    pipeline.advance(new.parent_job_id)
    gate = pipeline.advance(new.parent_job_id)
    assert gate.state == 'waiting_agent'
    assert gate.source_pdf_sha256 != result['final']['source_pdf_sha256']
    assert pipeline.advance(new.parent_job_id, {'full_translation': {}}).state == 'waiting_agent'
    assert (old_reader.read_bytes(), old_reader.stat().st_mtime_ns) == confirmed
    library = probe.LibraryService(data)
    try:
        candidate_artifact = tuple(library.conn.execute(
            "SELECT rel_path, status, updated_at FROM artifacts WHERE paper_id=? AND kind='reader'", (paper,)).fetchone())
        # Input change deliberately invalidates readiness; it must not replace bytes/path.
        assert candidate_artifact[:2] == (old_artifact[0], 'stale')
        print(json.dumps({'before': old_artifact, 'after': candidate_artifact,
                          'reader_sha256': probe.sha(old_reader), 'bytes_and_mtime_unchanged': True}))
    finally:
        library.close()
