"""Synthetic executable provider for the real CLI/launcher/worker path."""
import json, os, sys
from pathlib import Path
if '--version' in sys.argv:
    print('mineru 9.4.0')
    raise SystemExit(0)
args = sys.argv
pdf = Path(args[args.index('-p') + 1])
out = Path(args[args.index('-o') + 1])
root = Path(os.environ['V004H_CONTROL'])
with (root / 'provider-calls.jsonl').open('a', encoding='utf-8') as stream:
    stream.write(json.dumps({'pid': os.getpid(), 'pdf': str(pdf), 'output': str(out)}) + '\n')
marker = root / 'failed-once'
if not marker.exists():
    marker.write_text('controlled parse failure', encoding='utf-8')
    raise SystemExit(19)
out.mkdir(parents=True, exist_ok=True)
content = [dict(type='header', text='Load Distribution in Modular Truss Bridges', text_level=1, page_idx=0, bbox=[72,72,520,110])]
content += [dict(type='text', text=f'Synthetic engineering paragraph {i} on load and deflection.', page_idx=i//12, bbox=[72,120,520,145]) for i in range(42)]
(out / 'fixture_content_list.json').write_text(json.dumps(content), encoding='utf-8')

