import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { python } from './python-runtime.mjs';
import { engineResumeStoppedFullRead, engineContinueFullRead } from '../lib/index.js';
import { withEngineScope } from '../lib/engine_scope.js';

// This subprocess probe tests argument/environment transport only; the B card
// separately runs the actual Python module and persistent control service.
const root = await mkdtemp(join(tmpdir(), 'v02-004i-api-'));
const oldPath = process.env.PYTHONPATH;
try {
  await mkdir(join(root, 'scientific_reading'));
  await writeFile(join(root, 'scientific_reading', '__init__.py'), '');
  await writeFile(join(root, 'scientific_reading', '__main__.py'),
    `import json,os,sys\nprint(json.dumps(dict(args=sys.argv[1:], input=json.load(sys.stdin), scope=json.loads(os.environ['SR_SCOPE_CONTEXT']), wrapper=os.environ.get('SR_SCANSCI_PROVIDER_WRAPPER'), provider=os.environ.get('SR_SCANSCI_PROVIDER_PYTHON'), legal=os.environ.get('SR_SCANSCI_DISABLE_INSTITUTION'))))\n`);
  process.env.PYTHONPATH = root;
  const config = { dataRoot: join(root, 'data'), enginePython: python, scansciPython: python, school: '', outputDir: '', legalOnly: false };
  const scope = { instanceId: 'test', scopeSessionId: 'session', scopeFolderId: 'folder' };
  const input = { unicode: '停止恢复', value: 0 };
  const result = await withEngineScope(scope, () => engineResumeStoppedFullRead(config, 'job_test', input, { requestId: 'zero', expectedRevision: 0 }));
  assert.equal(result.exitCode, 0);
  assert.deepEqual(result.json.args, ['--data-root', config.dataRoot, 'full-read-pipeline-resume', '--job-id', 'job_test',
    '--resume-stopped', '--request-id', 'zero', '--expected-revision', '0', '--input', '-']);
  assert.deepEqual(result.json.input, input); assert.deepEqual(result.json.scope, scope);
  assert.equal(result.json.provider, python); assert.equal(result.json.legal, '1');
  assert.ok(result.json.wrapper.endsWith('scripts/scansci_wrap.py') || result.json.wrapper.endsWith('scripts\\scansci_wrap.py'));
  const legal = JSON.parse(await readFile(join(config.dataRoot, 'oa-downloader/config.json'), 'utf8'));
  assert.equal(legal.download_strategy, 'oa_only'); assert.equal(legal.scihub_enabled, false);
  const legacy = await withEngineScope(scope, () => engineContinueFullRead(config, 'job_test', input));
  assert.ok(!legacy.json.args.includes('--resume-stopped'));
  for (const options of [null, { requestId: '', expectedRevision: 0 }, { requestId: ' ', expectedRevision: 0 },
    { requestId: 'x'.repeat(201), expectedRevision: 0 }, ...[-1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '0'].map(expectedRevision => ({ requestId: 'r', expectedRevision }))]) {
    await assert.rejects(engineResumeStoppedFullRead({}, 'job_test', input, options), /reading_control_operation_invalid/);
  }
  console.log('PASS: explicit stop resume exports, exact arguments, input, trusted environment, scope, legacy compatibility and invalid options');
} finally {
  if (oldPath === undefined) delete process.env.PYTHONPATH; else process.env.PYTHONPATH = oldPath;
  await rm(root, { recursive: true, force: true });
}
