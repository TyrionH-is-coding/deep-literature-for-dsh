"""Installed real worker failure retained across host restarts; synthetic provider only."""
import sys, json, importlib.util, hashlib
from pathlib import Path
root=Path(sys.argv[1]);mode=sys.argv[2];fixture=Path(sys.argv[3])
spec=importlib.util.spec_from_file_location('fixture',fixture);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
control=root/'restart-failure-v3';data=root/'library';record=control/'expected.json'
if mode=='seed':
 control.mkdir(exist_ok=False)
 p.record_provenance(control/'provenance.json')
 p.atomic_write_json(control/'config.json',{'scenario':'parse-fail-before'})
 meta=p._metadata();meta.doi='10.5555/v02-004d-restart-failure-v3'
 library=p.LibraryService(data)
 try:paper=library.ingest(meta)['paper_id']
 finally:library.close()
 workspace=p.PaperWorkspace.create_for_paper_id(data,paper,meta);p._fixture_pdf(workspace.source_pdf)
 pipeline=p.ReadingPipeline(data,mineru_service=p.Parse(control),full_read_service=p.Full(control))
 parent=pipeline.start(paper).parent_job_id
 p.run_job(pipeline.job_store,parent,{'full_read_pipeline':p.full_read_pipeline_handler_factory(pipeline,pipeline_input=None)})
 status=pipeline.job_store.load_status(parent);assert status.state=='failed',status.to_dict()
 files={str(f.relative_to(root)):p.sha(f) for f in pipeline.job_store.handle(parent).root.glob('*.json')}
 value={'parent':parent,'paper':paper,'status':status.to_dict(),'files':files}
 p.atomic_write_json(record,value)
elif mode=='resume':
 value=p.read(record);pipeline=p.ReadingPipeline(data,mineru_service=p.Parse(control),full_read_service=p.Full(control))
 assert pipeline.inspect(value['parent']).state=='failed'
 pipeline.job_store.transition(value['parent'],'queued')
 p.run_job(pipeline.job_store,value['parent'],{'full_read_pipeline':p.full_read_pipeline_handler_factory(pipeline,pipeline_input={})})
 state=pipeline.inspect(value['parent'])
 assert state.state!='failed',state.to_dict()
 value={'parent':value['parent'],'afterExplicitResume':state.to_dict()}
else:
 value=p.read(record);store=p.BackgroundJobStore(data);status=store.load_status(value['parent'])
 assert status.state=='failed',status.to_dict()
 assert all(p.sha(root/f)==h for f,h in value['files'].items())
 value={'parent':value['parent'],'state':status.state,'unchanged':True}
print(json.dumps(value))
