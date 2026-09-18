"""Replay the exact archived 004D provider exception in a new isolated library."""
import importlib.util, json, os, tempfile
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
p=module('frozen_004d',repo/'docs/codex-v02/V02-004G-evidence/frozen-process-probe.py')
a=module('audit_004g',repo/'scripts/v02-004g-audit.py')
root=Path(tempfile.mkdtemp(prefix='g4d-'))
os.environ.clear();os.environ.update(a.env_for_saved(root))
p.atomic_write_json(root/'config.json',{'scenario':'parse-fail-before'})
meta=p._metadata();meta.doi='10.5555/v004g-original'
library=p.LibraryService(root/'data')
try:paper=library.ingest(meta)['paper_id']
finally:library.close()
workspace=p.PaperWorkspace.create_for_paper_id(root/'data',paper,meta);p._fixture_pdf(workspace.source_pdf)
pipeline=p.ReadingPipeline(root/'data',mineru_service=p.Parse(root),full_read_service=p.Full(root))
parent=pipeline.start(paper).parent_job_id
exit_code=p.run_job(pipeline.job_store,parent,{'full_read_pipeline':p.full_read_pipeline_handler_factory(pipeline,pipeline_input=None)})
result={'root':str(root),'worker_exit':exit_code,'parameters':{'parent_job_id':parent,'supplied_input':{}},'before':a.snapshot(pipeline,parent)}
result['returned']=pipeline.advance(parent,{}).to_dict()
result['after']=a.snapshot(pipeline,parent)
assert result['before']['status']['error']=='controlled_parse_fail_before'
assert result['returned']['state']=='queued'
assert 'reading_pipeline_state_invalid' in result['after']['inspect_traceback']
(repo/'docs/codex-v02/V02-004G-evidence/original-replay.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Exact 004D error reproduced; direct return queued, job failed, inspect invalid.')
