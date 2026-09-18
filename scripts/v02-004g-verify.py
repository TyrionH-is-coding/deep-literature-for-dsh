"""Verify the diagnostic evidence, frozen inputs, source identity and task-only scope."""
import hashlib,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
repo=Path(__file__).resolve().parents[1];out=repo/'docs/codex-v02/V02-004G-evidence'
def read(name):return json.loads((out/name).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for item in read('frozen-inputs.json'):assert sha(out/item['saved'])==item['sha256']
environment=read('environment.json')
for key,digest in environment['source_sha256'].items():
    package,relative=key.split('/',1)
    source=repo/('engine/src' if package=='scientific_reading' else 'engine')/package/relative
    assert sha(source)==digest
assert (out/'red-exit.txt').read_text().strip()=='1'
assert 'REGRESSION: accepted explicit advance' in (out/'red.txt').read_text(encoding='utf-8-sig')
assert (out/'original-replay-exit.txt').read_text().strip()=='0'
assert (out/'integrity-tests-exit.txt').read_text().strip()=='0'
assert '6 passed' in (out/'integrity-tests.txt').read_text()
a=read('audit.json');assert 'harness_traceback' not in a
for name in ('cli-resume','cli-start'):
    c=a['cases'][name];assert c['command']['exit']==0 and c['after']['status']['state']=='waiting_agent'
    assert 'inspect_traceback' not in c['after']
for name in ('cleanup.json','cleanup-first-run.json'):
    c=read(name);assert not c['live_owned_processes'] and not c['owner_json']
for target in re.findall(r'\]\(([^)]+)\)',(repo/'docs/codex-v02/V02-004G-report.md').read_text(encoding='utf-8-sig')):
    assert (repo/'docs/codex-v02'/target).exists(),target
base='a37a415c4bec9a895f1dc1619cfa35081cf85d26'
subprocess.run(['git','diff','--exit-code',base,'--','engine','src','tests','package.json','package-lock.json'],cwd=repo,check=True)
changes=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=repo,text=True).splitlines()
for line in changes:
    path=line[3:].strip('"')
    assert path.startswith(('docs/codex-v02/V02-004G','scripts/v02-004g-','scripts/fixtures/v02-004g/')),path
receipt=json.loads((repo/'docs/codex-v02/V02-004G-receipt.json').read_text(encoding='utf-8-sig'));assert receipt['phase']=='review'
result={'time':datetime.now(timezone.utc).isoformat(),'base':base,'contextCommit':receipt['contextCommit'],'source_files_verified':len(environment['source_sha256']),'frozen_inputs_verified':8,'red_exit':1,'integrity':'6 passed','original_replay_exit':0,'allowed_scope_only':True,'production_unchanged':True,'receipt_phase':'review','changes':changes}
(out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Evidence, source, links, review receipt and scope verified.')
