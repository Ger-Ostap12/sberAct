const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { converterManifest } = require('../build-update');
const { digest } = require('../../electron-app/update-package');

const project = path.resolve(__dirname, '../..');
const lockFile = path.join(project, 'scripts/ci/assets.lock.json');
const summary = groups => Object.fromEntries(Object.entries(groups).map(([key, files]) => [key, {
  files: files.length, bytes: files.reduce((sum, file) => sum + file.size, 0),
  sha256: crypto.createHash('sha256').update(JSON.stringify(files)).digest('hex'),
}]));
async function scan(directory, relative = '') {
  const files = [];
  if (!fs.existsSync(directory)) return files;
  for (const entry of fs.readdirSync(path.join(directory, relative), { withFileTypes: true }).sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)) {
    if (entry.name.startsWith('~$') || entry.name === '__pycache__') continue;
    const name = relative ? relative + '/' + entry.name : entry.name;
    const full = path.join(directory, name);
    if (entry.isSymbolicLink()) throw new Error('Asset contains a link: ' + name);
    if (entry.isDirectory()) files.push(...await scan(directory, name));
    else if (entry.isFile()) files.push({ path: name, size: fs.statSync(full).size, sha256: await digest(full) });
  }
  return files;
}
async function inputs() {
  const corpus = path.join(project, 'Заявления');
  const converter = path.join(project, 'release/converter');
  const models = path.join(project, 'python-backend/models');
  const payload = await converterManifest(converter, require('../../package.json').version);
  const files = [...payload.files, {
    path: 'converter-manifest.json',
    size: fs.statSync(path.join(converter, 'converter-manifest.json')).size,
    sha256: await digest(path.join(converter, 'converter-manifest.json')),
  }];
  const groups = { corpus: await scan(corpus), converter: files, models: await scan(models) };
  assert.ok(groups.corpus.length, 'Test corpus is missing');
  return { roots: { corpus, converter, models }, groups };
}
function outside(first, second) {
  const a = path.resolve(first).toLowerCase();
  const b = path.resolve(second).toLowerCase();
  return a !== b && !a.startsWith(b + path.sep) && !b.startsWith(a + path.sep);
}
function copyFiles(source, target, files) {
  for (const file of files) {
    assert.ok(file.path && !file.path.includes('\\') && !file.path.split('/').some(p => !p || p === '..' || p === '.' || p.includes(':')), 'Invalid asset path');
    const dest = path.join(target, file.path);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(source, file.path), dest, fs.constants.COPYFILE_EXCL);
  }
}
async function check(home, expected = JSON.parse(fs.readFileSync(lockFile, 'utf8'))) {
  assert.ok(outside(home, project), 'CI home must be outside the checkout');
  const index = JSON.parse(fs.readFileSync(path.join(home, 'assets/index.json'), 'utf8'));
  assert.deepEqual(summary(index), expected, 'Asset index does not match assets.lock.json');
  for (const [group, files] of Object.entries(index)) {
    let checked = 0;
    console.log('Checking CI assets: ' + group + ' (' + files.length + ' files)');
    for (const file of files) {
      const full = path.join(home, 'assets', group, file.path);
      assert.ok(fs.existsSync(full) && fs.statSync(full).size === file.size, 'CI asset is missing or changed: ' + group + '/' + file.path);
      assert.equal(await digest(full), file.sha256, 'CI asset hash differs: ' + group + '/' + file.path);
      if (++checked % 2000 === 0) console.log('Checked CI assets: ' + group + ' ' + checked + '/' + files.length);
    }
  }
  return index;
}
async function main(args) {
  const command = args.shift();
  const home = path.resolve(process.env.SBERACT_CI_HOME || 'C:/Диск D/Сбер/SberAct-CI');
  if (command === 'lock') {
    const { groups } = await inputs();
    fs.writeFileSync(lockFile, JSON.stringify(summary(groups), null, 2) + '\n');
    console.log('CI asset fingerprints saved; no input documents or OCR files added to the repository.');
  } else if (command === 'prepare') {
    assert.ok(outside(home, project), 'CI home must be outside the project');
    const { roots, groups } = await inputs();
    assert.deepEqual(summary(groups), JSON.parse(fs.readFileSync(lockFile, 'utf8')), 'Inputs differ from assets.lock.json; review changes and run lock first');
    const target = path.join(home, 'assets');
    assert.ok(!fs.existsSync(target), 'CI assets already exist; use a new CI home to prepare a new snapshot');
    const python = path.resolve(args[0] || path.join(project, 'python-backend/venv/Scripts/python.exe'));
    assert.ok(fs.existsSync(python), 'Backend Python does not exist');
    fs.mkdirSync(target, { recursive: true });
    for (const [group, files] of Object.entries(groups)) copyFiles(roots[group], path.join(target, group), files);
    fs.writeFileSync(path.join(target, 'index.json'), JSON.stringify(groups));
    await check(home);
    fs.writeFileSync(path.join(home, 'settings.json'), JSON.stringify({ python }, null, 2));
    console.log('CI assets prepared in ' + home);
  } else if (command === 'restore') {
    assert.equal(process.env.GITHUB_ACTIONS, 'true', 'Restore is only allowed inside GitHub Actions');
    assert.equal(path.resolve(process.env.GITHUB_WORKSPACE), project, 'Unexpected Actions checkout');
    const groups = await check(home);
    const targets = { corpus: 'Заявления', converter: 'release/converter', models: 'python-backend/models' };
    for (const [group, files] of Object.entries(groups)) {
      const target = path.join(project, targets[group]);
      for (const file of files) {
        const dest = path.join(target, file.path);
        if (fs.existsSync(dest)) {
          assert.equal(await digest(dest), file.sha256, 'Tracked file differs from CI snapshot: ' + file.path);
        } else copyFiles(path.join(home, 'assets', group), target, [file]);
      }
    }
    const settings = JSON.parse(fs.readFileSync(path.join(home, 'settings.json'), 'utf8'));
    assert.ok(settings.python && !/[\r\n]/.test(settings.python) && fs.existsSync(settings.python), 'CI Python is not configured');
    fs.appendFileSync(process.env.GITHUB_ENV, 'CI_PYTHON=' + settings.python + '\n');
    console.log('Pinned corpus, OCR and backend models restored.');
  } else if (command === 'publish') {
    assert.equal(process.env.GITHUB_ACTIONS, 'true', 'Publish is only allowed inside GitHub Actions');
    assert.ok(outside(home, project), 'CI home must be outside the checkout');
    const version = require('../../package.json').version;
    const id = process.env.GITHUB_RUN_ID + '-' + process.env.GITHUB_RUN_ATTEMPT + '-' + process.env.GITHUB_SHA;
    assert.match(id, /^\d+-\d+-[a-f0-9]{40}$/);
    const output = path.join(home, 'artifacts', version, id);
    const source = path.join(project, 'release/SberAct-Update');
    const files = await scan(source);
    assert.ok(files.length, 'No build output');
    assert.ok(!fs.existsSync(output), 'Build output already exists');
    copyFiles(source, output, files);
    fs.copyFileSync(path.join(project, 'release/full-package-verification.json'), path.join(output, 'full-package-verification.json'));
    fs.writeFileSync(path.join(output, 'build-info.json'), JSON.stringify({ version, commit: process.env.GITHUB_SHA, run: id, runner: process.env.RUNNER_NAME, assets: JSON.parse(fs.readFileSync(lockFile, 'utf8')) }, null, 2));
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, 'Windows ' + version + ' built and verified. Full offline package on runner: ' + output + '\n');
    console.log('Build saved: ' + output);
  } else if (command === 'reports') {
    assert.equal(process.env.GITHUB_ACTIONS, 'true');
    assert.ok(outside(home, project));
    const id = process.env.GITHUB_RUN_ID + '-' + process.env.GITHUB_RUN_ATTEMPT;
    assert.match(id, /^\d+-\d+$/);
    const source = path.join(project, 'temp/ci');
    if (fs.existsSync(source)) copyFiles(source, path.join(home, 'reports', id), await scan(source));
  } else throw new Error('Usage: node scripts/ci/assets.js lock|prepare [python.exe]|restore|publish|reports');
}
module.exports = { summary, outside, check };
if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });
