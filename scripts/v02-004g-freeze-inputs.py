"""Read immutable B blobs only; never open the archived instance paths."""
import hashlib,json,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1];out=repo/'docs/codex-v02/V02-004G-evidence'
context='fd1e08d2d35c13af8723a93b794187ea6d87a021'
paths=['AGENTS.md','docs/project/session-protocol.md','docs/project/tasks/V02-004G.md','docs/project/evidence/V02-004D-control-review.md','docs/project/evidence/V02-004D/restart-failure-direct-advance.json','docs/project/evidence/V02-004D/restart-failure-direct-advance.txt','scripts/fixtures/v02-004d/restart-failure.py','scripts/fixtures/v02-004d/process-probe.py']
values=[]
for path in paths:
    raw=subprocess.check_output(['git','-C','C:/Users/15694/Documents/ChatGPT/deep-literature-for-codex','show',context+':'+path])
    target=out/('frozen-'+Path(path).name);target.write_bytes(raw)
    values.append({'contextCommit':context,'source':path,'saved':target.name,'sha256':hashlib.sha256(raw).hexdigest()})
(out/'frozen-inputs.json').write_text(json.dumps(values,indent=2),encoding='utf-8')
print('Archived',len(values),'immutable blobs byte-for-byte.')
