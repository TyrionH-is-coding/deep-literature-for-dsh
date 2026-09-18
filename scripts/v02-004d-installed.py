"""Run unchanged 004A/004B assertions against installed packages, via stdlib adapter."""
import importlib.util, json, sys, tempfile, time
from pathlib import Path
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
def load(name):
 spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name('v02-004d-'+name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
n=load('negative');c=load('contract');n.p.record_provenance(out/'assertions-provenance.json')
results=[]
def run(label, fn):
 start=time.time()
 try: fn();results.append(dict(name=label,passed=True,seconds=time.time()-start))
 except Exception as e:
  import traceback
  results.append(dict(name=label,passed=False,error=traceback.format_exc(),seconds=time.time()-start))
 (out/'assertions.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
 print(label,results[-1]['passed'],flush=True)
def pending(fn,*args):
 gen=n.pending();value=next(gen)
 try:fn(value,*args)
 finally:gen.close()
for flag in (False,True):
 run('running source '+str(flag),lambda:pending(n.test_same_source_running_checkpoint_retries,flag))
 run('require completed '+str(flag),lambda:pending(n.test_running_never_satisfies_require_stage,flag))
for mutation in ['explicit_other_sha','explicit_null_sha','completed_missing_sha','completed_other_sha','failed','queued','wrong_job_status','pdf_unconfirmed','pdf_hash_missing','pdf_hash_other','missing_generation_source','changed_generation_source','changed_base_source','metadata','directory_identity','published_target','published_manifest','other_stage']:
 run('reject twice '+mutation,lambda:pending(n.test_legacy_exception_rejects_conflicts,mutation))
run('confirmed cache corruption',lambda:pending(n.test_confirmed_cache_corruption_never_calls_provider))
for boundary in c.probe.SCENARIOS:
 run('process '+boundary,lambda:c.test_cross_process_stage_recovery(out/boundary,boundary))
(out/'atomic').mkdir()
run('translation atomic protection',lambda:c.test_duplicate_translation_and_incomplete_candidate_are_non_destructive(out/'atomic'))
run('published Reader protection',lambda:c.test_incomplete_new_generation_preserves_published_reader(out/'reader'))
run('cancel remains gap',c.test_engine_has_no_cancel_state_or_cli_command)
raise SystemExit(int(any(not r['passed'] for r in results)))
