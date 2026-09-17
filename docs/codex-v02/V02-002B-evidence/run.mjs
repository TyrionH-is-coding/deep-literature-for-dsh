import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
const root = resolve(import.meta.dirname, '../../..')
const out = resolve(root, 'docs/codex-v02/V02-002B-evidence')
const python = resolve(root, '.venv/Scripts/python.exe')
const env = { ...process.env, SCIENTIFIC_READING_PYTHON: python, PYTHON: python,
  PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', SR_NATIVE_KEYRING_TEST: '0',
  PIP_NO_BUILD_ISOLATION: '1', PIP_CONSTRAINT: resolve(root, 'docs/codex-v02/evidence/audit-python-requirements.txt') }
const commands = {
  build: 'npm run build:ci',
  before: 'node tests/navigation-contract.mjs',
  after: 'node tests/navigation-contract.mjs',
  offline: 'npm run test:offline',
  assets: 'npm run test:assets',
}
const id = process.argv[2]
if (!Object.hasOwn(commands, id)) throw new Error('Expected build, before, after, offline, or assets')
const command = commands[id]
const startedAt = new Date().toISOString()
const run = spawnSync(command, { cwd: root, env, shell: true, encoding: 'utf8', timeout: 600000, maxBuffer: 32 * 1024 * 1024, windowsHide: true })
writeFileSync(resolve(out, `${id}.log`), `$ ${command}\n${run.stdout ?? ''}${run.stderr ?? ''}${run.error ? '\n' + run.error.stack : ''}`)
const path = resolve(out, 'test-runs.json')
const results = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : []
results.push({ id, command, startedAt, finishedAt: new Date().toISOString(), exitCode: run.status, signal: run.signal, error: run.error?.message ?? null })
writeFileSync(path, JSON.stringify(results, null, 2) + '\n')
console.log(`${id}: exit=${run.status}\n${run.stdout ?? ''}${run.stderr ?? ''}`)
process.exitCode = run.status ?? 1
