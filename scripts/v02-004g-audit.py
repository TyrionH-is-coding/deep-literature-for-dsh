"""004G standalone diagnostic. Default records observations; --expect-direct-safe is a RED regression probe."""
import argparse, hashlib, json, os, subprocess, sys, tempfile, time, traceback
from pathlib import Path
from scientific_reading.reading_pipeline import ReadingPipeline
from scientific_reading.reading_pipeline_models import ReadingPipelineState
from scientific_reading.library_service import LibraryService
from scientific_reading.models import PaperMetadata
from scientific_reading.workspace import PaperWorkspace
from scientific_reading.worker import run_job, full_read_pipeline_handler_factory
from scientific_reading.background_models import AgentRequired
from scientific_reading.background_launcher import process_start_identity

REPO = Path(__file__).resolve().parents[1]
OUT = REPO/'docs/codex-v02/V02-004G-evidence'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot(pipeline, parent):
    handle = pipeline.job_store.handle(parent)
    result = {'pipeline': read(handle.reading_pipeline_path), 'status': read(handle.status_path),
              'request':read(handle.request_path), 'events': pipeline.job_store.read_events(parent),
              'checkpoints': {str(p.relative_to(pipeline.data_root)):read(p) for p in pipeline.data_root.glob('papers/**/job.json')},
              'hashes': {p.name:digest(p) for p in handle.root.glob('*.json')}}
    try:
        result['inspect'] = pipeline.inspect(parent).to_dict()
    except Exception:
        result['inspect_traceback'] = traceback.format_exc()
    state = ReadingPipelineState.from_dict(result['pipeline'])
    result['validator_by_job_state'] = {}
    for job_state in ('failed','queued','running','waiting_agent'):
        try:
            pipeline._validate_state(state,parent,expected_paper_id=state.paper_id,job_state=job_state)
            result['validator_by_job_state'][job_state] = 'valid'
        except ValueError as error:
            result['validator_by_job_state'][job_state] = str(error)
    return result

def env_for(control):
    env = {k:v for k,v in os.environ.items() if k in {'SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','PATH','PATHEXT'}}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',SR_NATIVE_KEYRING_TEST='0',
               MINERU_EXECUTABLE=str(Path(sys.prefix)/'Scripts/v004g-provider.exe'),V004G_CONTROL=str(control))
    return env

def cli(data, control, *args):
    command = [sys.executable,'-I','-X','utf8','-m','scientific_reading','--data-root',str(data),*args]
    result = subprocess.run(command,env=env_for(control),capture_output=True,text=True,encoding='utf-8',timeout=30,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr)

def wait_worker(pipeline,parent):
    store = pipeline.job_store
    deadline = time.monotonic()+40
    marker_path = store.handle(parent).root/'launch.json'
    marker = None
    while time.monotonic()<deadline:
        if marker_path.exists():
            marker = read(marker_path)
        status = store.load_status(parent)
        alive = bool(marker and marker.get('pid') and store._pid_is_alive(marker['pid']))
        if status.state not in ('queued','running') and marker and not alive:
            return {'marker':marker,'alive_after':False,'status':status.to_dict()}
        time.sleep(.05)
    # Only this library's launch marker with verified creation identity is eligible.
    if marker and marker.get('pid') and process_start_identity(marker['pid'])==marker.get('process_start_identity'):
        import signal
        os.kill(marker['pid'], signal.SIGTERM)
    raise TimeoutError('owned worker did not finish')

def seed(root,name,via_cli=False):
    control=root/name
    control.mkdir()
    data=control/'data'
    meta=PaperMetadata(title='Load Distribution in Modular Truss Bridges',authors=['Alex Rivera'],doi='10.5555/v004g-'+name,year=2026,journal='Fictional Engineering Notes')
    library=LibraryService(data)
    try: paper=library.ingest(meta)['paper_id']
    finally: library.close()
    ws=PaperWorkspace.create_for_paper_id(data,paper,meta)
    pages=['Load Distribution in Modular Truss Bridges\nAbstract\nA fictional engineering fixture.','Methods\nFinite element mesh, load cases, and boundary conditions.','Results\nFigure 1 stress field. Figure 2 displacement. Table 1 load cases.','References\n[1] Rivera A. Fictional bridge benchmark. 2026.']
    ws.source_pdf.write_bytes(b'%PDF-1.4\n% offline fixture\n'+'\n\f\n'.join(pages).encode()+b'\n%%EOF\n')
    pipeline=ReadingPipeline(data)
    parent=pipeline.start(paper).parent_job_id
    os.environ.clear();os.environ.update(env_for_saved(control))
    initial={}
    if via_cli:
        initial['command']=cli(data,control,'full-read-pipeline-start','--paper-id',paper)
        assert initial['command']['exit']==0, initial
        initial['process']=wait_worker(pipeline,parent)
    else:
        initial['worker_exit']=run_job(pipeline.job_store,parent,{'full_read_pipeline':full_read_pipeline_handler_factory(pipeline)})
    initial['snapshot']=snapshot(pipeline,parent)
    assert initial['snapshot']['status']['state']=='failed',initial
    assert initial['snapshot']['pipeline']['current_stage']=='parse_mineru',initial
    assert 'inspect_traceback' not in initial['snapshot'],initial
    return control,pipeline,parent,initial

BASE_ENV=os.environ.copy()
def env_for_saved(control):
    # Never carry provider credentials or scopes from the caller.
    env={k:v for k,v in BASE_ENV.items() if k in {'SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','PATH','PATHEXT'}}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',SR_NATIVE_KEYRING_TEST='0',MINERU_EXECUTABLE=str(Path(sys.prefix)/'Scripts/v004g-provider.exe'),V004G_CONTROL=str(control))
    return env

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expect-direct-safe',action='store_true');args=parser.parse_args()
    root=Path(tempfile.mkdtemp(prefix='g4-'))
    report={'root':str(root),'python':sys.executable,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'cases':{},'cleanup':[]}
    try:
        for name in ('direct-none','direct-success','direct-refail','direct-gate','cli-resume','cli-start'):
            control,pipeline,parent,initial=seed(root,name,name.startswith('cli'))
            case={'initial':initial,'parameters':{'parent_job_id':parent,'supplied_input':None if name=='direct-none' else {}}}
            report['cases'][name]=case
            if name.startswith('direct'):
                if name=='direct-refail':
                    def runner(*_): raise RuntimeError('controlled_refail')
                    pipeline.stage_runner=runner
                if name=='direct-gate':
                    def runner(*_): raise AgentRequired('controlled_gate',{'stage':'parse_mineru'})
                    pipeline.stage_runner=runner
                try: case['returned']=pipeline.advance(parent,None if name=='direct-none' else {}).to_dict()
                except Exception: case['advance_traceback']=traceback.format_exc()
            else:
                bad=control/'invalid.json';bad.write_text('{"unexpected":true}',encoding='utf-8')
                case['rejected_nonempty']=cli(pipeline.data_root,control,'full-read-pipeline-resume','--job-id',parent,'--input',str(bad))
                assert case['rejected_nonempty']['exit']==4
                assert snapshot(pipeline,parent)['hashes']==initial['snapshot']['hashes']
                command=('full-read-pipeline-resume','--job-id',parent) if name=='cli-resume' else ('full-read-pipeline-start','--paper-id',initial['snapshot']['pipeline']['paper_id'])
                case['command']=cli(pipeline.data_root,control,*command)
                assert case['command']['exit']==0,case['command']
                case['process']=wait_worker(pipeline,parent)
                report['cleanup'].extend([initial['process'],case['process']])
            case['after']=snapshot(pipeline,parent)
            case['provider_calls']=[json.loads(line) for line in (control/'provider-calls.jsonl').read_text().splitlines()]
            if name=='direct-none': assert initial['snapshot']['hashes']==case['after']['hashes']
            if name in ('direct-success','direct-gate') and not args.expect_direct_safe:
                assert 'reading_pipeline_state_invalid' in case['after'].get('inspect_traceback','')
                assert case['after']['validator_by_job_state']['running']=='valid'
            if name=='direct-refail': assert 'inspect_traceback' not in case['after']
            if name.startswith('cli'):
                assert 'inspect_traceback' not in case['after']
                assert case['after']['status']['state']=='waiting_agent'
                assert case['after']['status']['reason_code']=='translate_full_read'
                assert case['after']['pipeline']['stage_timings']['parse_mineru']['finished_at'] is not None
                assert len(case['provider_calls'])==2
        report['diagnosis']='terminal job state mismatch; explicit direct advance mutates pipeline without background state synchronization'
    except Exception:
        report['harness_traceback']=traceback.format_exc()
        raise
    finally:
        (OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({name:{'job':c['after']['status']['state'],'pipeline':c['after']['pipeline']['state'],'stage':c['after']['pipeline']['current_stage'],'inspect_ok':'inspect_traceback' not in c['after']} for name,c in report['cases'].items()},indent=2))
    if args.expect_direct_safe:
        case = report['cases']['direct-success']
        assert 'inspect_traceback' not in case['after'], 'REGRESSION: accepted explicit advance must leave reloadable state (or reject before mutation)'
        if 'advance_traceback' in case:
            assert case['initial']['snapshot']['hashes'] == case['after']['hashes'], 'REGRESSION: rejection must precede mutation'

if __name__=='__main__':main()
