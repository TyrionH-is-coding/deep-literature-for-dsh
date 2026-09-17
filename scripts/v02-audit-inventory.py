"""Generate per-file baseline test counts and static direct Python dependencies."""
import ast
import json
from pathlib import Path
import platform
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/codex-v02/evidence'
groups = [
    ('storage-and-scope', ('library', 'scope', 'data_guard', 'generation_package', 'candidate', 'atomic_json')),
    ('pipeline-and-jobs', ('reading_pipeline', 'background', 'worker_full', 'foreground', 'pid', 'subprocess')),
    ('acquisition-and-parse', ('mineru', 'pdf', 'parse_models', 'normalization', 'scansci', 'metadata_enrichment')),
    ('reading-and-review', ('full_read', 'review', 'reader', 'abstract_read')),
    ('derived-and-assets', ('xlsx', 'excel', 'export', 'evidence', 'artifact', 'classification')),
]
def group(name):
    return next((g for g, keys in groups if any(k in name for k in keys)), 'platform-and-environment')

files = {}
for case in ET.parse(OUT / 'python-junit.xml').iter('testcase'):
    name = case.attrib['classname'].split('.')[-1] + '.py'
    row = files.setdefault(name, {'group': group(name), 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0, 'seconds': 0})
    state = 'failed' if case.find('failure') is not None else 'errors' if case.find('error') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
    row[state] += 1
    row['seconds'] += float(case.attrib.get('time', 0))
dependencies = {}
for path in sorted((ROOT / 'engine/src/scientific_reading').glob('*.py')):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    dependencies[path.name] = sorted({n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level})
node = json.loads((OUT / 'test-runs.json').read_text())
extra = json.loads((OUT / 'node-navigation-extra.json').read_text(encoding='utf-8-sig'))
(OUT / 'test-map.json').write_text(json.dumps({'pythonFiles': files, 'pythonDirectRelativeImports': dependencies, 'nodeRuns': [r for r in node if r['id'].startswith('test-')], 'extraNavigationRun': extra}, indent=2) + '\n', encoding='utf-8')
lines = ['# V02-002 existing Python tests by file', '', 'Generated from the recorded JUnit result; groups are audit labels, not new production modules.', '', '| Group | File | Pass | Fail | Error | Skip |', '| --- | --- | ---: | ---: | ---: | ---: |']
for name, row in sorted(files.items(), key=lambda pair: (pair[1]['group'], pair[0])):
    lines.append(f"| {row['group']} | `engine/tests/{name}` | {row['passed']} | {row['failed']} | {row['errors']} | {row['skipped']} |")
(OUT.parent / 'test-map.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
environment = {'platform': platform.platform(), 'python': platform.python_version(), 'git': subprocess.check_output(['git', '--version'], cwd=ROOT, text=True).strip(), 'node': subprocess.check_output(['node', '--version'], cwd=ROOT, text=True).strip(), 'npm': subprocess.check_output(['npm.cmd', '--version'], cwd=ROOT, text=True).strip(), 'typescript': subprocess.check_output(['node', 'node_modules/typescript/bin/tsc', '--version'], cwd=ROOT, text=True).strip(), 'coreAutocrlf': subprocess.check_output(['git', 'config', '--get', 'core.autocrlf'], cwd=ROOT, text=True).strip()}
(OUT / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'pythonFiles': len(files), 'totals': {k: sum(v[k] for v in files.values()) for k in ('passed', 'failed', 'errors', 'skipped')}, 'nodeRunsRecorded': len(node)}, indent=2))
