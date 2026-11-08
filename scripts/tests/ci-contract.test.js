const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { spawnSync } = require('node:child_process');
const yaml = require('js-yaml');
const { validate } = require('../ci/release-metadata');
const { outside, summary } = require('../ci/assets');
const root = path.resolve(__dirname, '../..');

function fixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sberact-ci-test-'));
  fs.mkdirSync(path.join(dir, 'electron-app'));
  for (const prefix of ['', 'electron-app/']) {
    fs.writeFileSync(path.join(dir, prefix + 'package.json'), JSON.stringify({ version: '2.1.3', dependencies: { example: '1.0.0' } }));
    fs.writeFileSync(path.join(dir, prefix + 'package-lock.json'), JSON.stringify({
      version: '2.1.3', packages: { '': { version: '2.1.3', dependencies: { example: '1.0.0' } } },
    }));
  }
  fs.writeFileSync(path.join(dir, 'CHANGELOG.md'), '## 2.1.3 — 08.11.2026\n\n- Исправления.\n');
  return dir;
}
function remove(dir) {
  const full = fs.realpathSync(dir);
  assert.equal(path.dirname(full).toLowerCase(), fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-ci-test-'));
  fs.rmSync(full, { recursive: true, force: true });
}
test('release metadata accepts a complete newer release', () => {
  const dir = fixture();
  try { assert.equal(validate(dir, '2.1.2'), '2.1.3'); }
  finally { remove(dir); }
});
for (const [name, change] of [
  ['frontend version', dir => { const file = path.join(dir, 'electron-app/package.json'); const data = JSON.parse(fs.readFileSync(file)); data.version = '2.1.2'; fs.writeFileSync(file, JSON.stringify(data)); }],
  ['lock root version', dir => { const file = path.join(dir, 'package-lock.json'); const data = JSON.parse(fs.readFileSync(file)); data.packages[''].version = '2.1.2'; fs.writeFileSync(file, JSON.stringify(data)); }],
  ['lock dependencies', dir => { const file = path.join(dir, 'electron-app/package-lock.json'); const data = JSON.parse(fs.readFileSync(file)); data.packages[''].dependencies.example = '2.0.0'; fs.writeFileSync(file, JSON.stringify(data)); }],
  ['release notes', dir => fs.writeFileSync(path.join(dir, 'CHANGELOG.md'), '## 2a1a3 — 08.11.2026\n\n- Invalid.\n')],
]) test('release metadata rejects inconsistent ' + name, () => {
  const dir = fixture();
  try { change(dir); assert.throws(() => validate(dir)); }
  finally { remove(dir); }
});
test('release metadata rejects equal or older version than main', () => {
  const dir = fixture();
  try { for (const version of ['2.1.3', '2.1.4']) assert.throws(() => validate(dir, version)); }
  finally { remove(dir); }
});
test('asset fingerprints detect content changes and paths cannot overlap', () => {
  const a = { corpus: [{ path: 'input.docx', size: 10, sha256: 'a'.repeat(64) }] };
  const b = { corpus: [{ path: 'input.docx', size: 10, sha256: 'b'.repeat(64) }] };
  assert.notEqual(summary(a).corpus.sha256, summary(b).corpus.sha256);
  assert.equal(outside(root, path.join(root, 'assets')), false);
  assert.equal(outside(root, root), false);
});
test('restore and publish refuse execution in the developer checkout', () => {
  for (const operation of ['restore', 'publish']) {
    const result = spawnSync(process.execPath, [path.join(root, 'scripts/ci/assets.js'), operation], {
      encoding: 'utf8', env: { ...process.env, GITHUB_ACTIONS: 'false' },
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /only allowed inside GitHub Actions/);
  }
});
test('workflow requires successful checks before main builds', () => {
  const workflow = yaml.load(fs.readFileSync(path.join(root, '.github/workflows/windows.yml'), 'utf8'));
  assert.deepEqual(workflow.on.push.branches, ['release', 'main']);
  assert.deepEqual(workflow.on.pull_request.branches, ['release', 'main']);
  assert.equal(workflow.permissions.contents, 'read');
  assert.equal(workflow.concurrency['cancel-in-progress'], false);
  const job = workflow.jobs.windows;
  assert.equal(job.needs, 'policy');
  assert.deepEqual(job['runs-on'], ['self-hosted', 'Windows', 'X64', 'sberact']);
  const steps = job.steps;
  const backend = steps.findIndex(step => step.name === 'Test complete backend including golden corpora');
  assert.match(steps[backend].run, /--require-golden-corpus/);
  for (const step of steps) assert.equal(step['continue-on-error'], undefined);
  for (const name of ['Build backend', 'Build Windows installer', 'Build complete offline update', 'Save full release on runner']) {
    const index = steps.findIndex(step => step.name === name);
    assert.ok(index > backend, name);
    assert.match(steps[index].if, /github.ref == 'refs\/heads\/main'/);
    assert.match(steps[index].if, /github.event_name != 'pull_request'/);
  }
  assert.match(steps.find(step => step.name === 'Build Windows installer').run, /--publish never/);
});

test('pinned assets reject missing files and corruption even at the same size', async () => {
  const dir = fixture();
  try {
    const assets = path.join(dir, 'assets');
    fs.mkdirSync(path.join(assets, 'corpus'), { recursive: true });
    const contents = Buffer.from('input');
    const record = { path: 'input.docx', size: contents.length, sha256: require('node:crypto').createHash('sha256').update(contents).digest('hex') };
    const groups = { corpus: [record] };
    const expected = summary(groups);
    fs.writeFileSync(path.join(assets, 'index.json'), JSON.stringify(groups));
    const { check } = require('../ci/assets');
    await assert.rejects(check(dir, expected), /missing or changed/);
    fs.writeFileSync(path.join(assets, 'corpus/input.docx'), contents);
    await check(dir, expected);
    fs.writeFileSync(path.join(assets, 'corpus/input.docx'), 'INPUT');
    await assert.rejects(check(dir, expected), /hash differs/);
    groups.corpus[0].sha256 = 'a'.repeat(64);
    fs.writeFileSync(path.join(assets, 'index.json'), JSON.stringify(groups));
    await assert.rejects(check(dir, expected), /index does not match/);
  } finally { remove(dir); }
});
