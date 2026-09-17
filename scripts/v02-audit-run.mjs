// V02-002: run existing offline suites independently; retain every exit code.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
const root = resolve(import.meta.dirname, '..')
const out = resolve(root, 'docs/codex-v02/evidence')
mkdirSync(out, { recursive: true })
const python = resolve(root, '.venv/Scripts/python.exe')
const env = { ...process.env, SCIENTIFIC_READING_PYTHON: python, PYTHON: python,
  PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', SR_NATIVE_KEYRING_TEST: '0',
  PIP_NO_BUILD_ISOLATION: '1', PIP_CONSTRAINT: resolve(out, 'audit-python-requirements.txt') }
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))
const entries = [
  ['build', 'npm run build:ci'],
  ['python', 'node scripts/run-python.mjs -m pytest -q -ra engine/tests --junitxml=docs/codex-v02/evidence/python-junit.xml'],
  ...['test:offline', 'test:assets'].flatMap(group => pkg.scripts[group].split(' && ').map((cmd, i) => [group.replace(':', '-') + '-' + String(i + 1).padStart(2, '0'), cmd])),
]
const results = []
for (const [id, command] of entries) {
  const startedAt = new Date().toISOString()
  const run = spawnSync(command, { cwd: root, env, shell: true, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024, windowsHide: true })
  writeFileSync(resolve(out, `${id}.log`), `$ ${command}\n${run.stdout ?? ''}${run.stderr ?? ''}${run.error ? '\n' + run.error.stack : ''}`)
  results.push({ id, command, startedAt, finishedAt: new Date().toISOString(), exitCode: run.status, signal: run.signal, error: run.error?.message ?? null })
  writeFileSync(resolve(out, 'test-runs.json'), JSON.stringify(results, null, 2) + '\n')
  console.log(`${id}: exit=${run.status} ${command}`)
  if (id === 'build' && run.status !== 0) break
}
process.exitCode = results.some(r => r.exitCode !== 0) ? 1 : 0
