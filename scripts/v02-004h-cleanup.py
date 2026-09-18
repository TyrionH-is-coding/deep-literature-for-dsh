"""Check only the task-owned synthetic CLI root and recorded process identities."""
import json
from pathlib import Path
from scientific_reading.background_store import BackgroundJobStore
from scientific_reading.background_launcher import process_start_identity
out = Path(__file__).resolve().parents[1] / 'docs/codex-v02/V02-004H-evidence'
audit = json.loads((out / 'audit.json').read_text())
root = Path(audit['root']).resolve()
assert root.parent == Path('C:/tmp') and root.name.startswith('h4-')
records = []
for marker in root.glob('**/launch.json'):
    value = json.loads(marker.read_text())
    pid = value['pid']
    records.append(dict(type='worker', path=str(marker), pid=pid,
                        recordedIdentity=value.get('process_start_identity'),
                        currentIdentity=process_start_identity(pid),
                        alive=BackgroundJobStore._pid_is_alive(pid)))
for calls in root.glob('*/provider-calls.jsonl'):
    for line in calls.read_text().splitlines():
        pid = json.loads(line)['pid']
        records.append(dict(type='provider', path=str(calls), pid=pid,
                            alive=BackgroundJobStore._pid_is_alive(pid)))
claims = [str(p) for p in root.glob('**/owner.json')]
result = dict(root=str(root), processes=records, ownerClaims=claims,
              cleanup='Synthetic files and private environment retained for review; no user files touched.')
(out / 'cleanup.json').write_text(json.dumps(result, indent=2))
assert not claims and not any(r['alive'] for r in records), result
print('All recorded workers/providers exited; no owner claims.')
