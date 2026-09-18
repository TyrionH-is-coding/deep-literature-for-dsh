"""Read-only final liveness/claims audit for the two roots recorded by this task."""
import json
from pathlib import Path
from scientific_reading.background_store import BackgroundJobStore
from scientific_reading.background_launcher import process_start_identity
repo=Path(__file__).resolve().parents[1];out=repo/'docs/codex-v02/V02-004G-evidence'
a=json.loads((out/'audit.json').read_text(encoding='utf-8'));b=json.loads((out/'original-replay.json').read_text(encoding='utf-8'))
roots=[Path(a['root']),Path(b['root'])];records=[]
for root in roots:
    assert root.parent==Path(__import__('tempfile').gettempdir()) and root.name.startswith(('g4-','g4d-'))
    for marker in root.glob('**/launch.json'):
        value=json.loads(marker.read_text());pid=value['pid']
        records.append({'type':'worker','marker':str(marker),'pid':pid,'recorded_identity':value.get('process_start_identity'),'current_identity':process_start_identity(pid),'alive':BackgroundJobStore._pid_is_alive(pid)})
    for calls in root.glob('*/provider-calls.jsonl'):
        for line in calls.read_text().splitlines():
            pid=json.loads(line)['pid'];records.append({'type':'provider','record':str(calls),'pid':pid,'alive':BackgroundJobStore._pid_is_alive(pid)})
claims=[str(p) for root in roots for p in root.glob('**/owner.json')]
result={'roots':[str(r) for r in roots],'processes':records,'live_owned_processes':[r for r in records if r['alive']],'owner_json':claims,'cleanup':'all observed children exited naturally; no kill needed; synthetic files retained'}
(out/'cleanup.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert not result['live_owned_processes'] and not claims,result
print('No live recorded workers/providers; no owner claims.')
