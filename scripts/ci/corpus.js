const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { scan, summary, outside } = require('./assets');
const { digest } = require('../../electron-app/update-package');

const root = path.resolve(__dirname, '../..');
const expected = JSON.parse(fs.readFileSync(path.join(__dirname, 'assets.lock.json'), 'utf8')).corpus;
async function verify(directory, fingerprint = expected) {
  const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'corpus-manifest.json'), 'utf8'));
  if (manifest.schema !== 1 || !Array.isArray(manifest.files)) throw new Error('Invalid private corpus manifest');
  const files = await scan(path.join(directory, 'corpus'));
  if (!files.length || JSON.stringify(summary({ corpus: files }).corpus) !== JSON.stringify(fingerprint)) {
    throw new Error('Private corpus differs from the pinned fingerprint');
  }
  if (JSON.stringify(files) !== JSON.stringify(manifest.files)) throw new Error('Private corpus manifest differs from files');
  return files;
}
async function prepare(home) {
  assert.ok(outside(home, root), 'CI home must be outside the project');
  const index = JSON.parse(fs.readFileSync(path.join(home, 'assets/index.json'), 'utf8'));
  if (JSON.stringify(summary({ corpus: index.corpus }).corpus) !== JSON.stringify(expected)) throw new Error('Snapshot differs from the pinned corpus');
  const output = path.join(home, 'exports/verification-data');
  assert.ok(!fs.existsSync(output), 'Export already exists; refusing to overwrite');
  const source = path.join(home, 'assets/corpus');
  for (const file of index.corpus) {
    const full = path.join(source, file.path);
    if (await digest(full) !== file.sha256) throw new Error('Snapshot corpus checksum differs');
  }
  fs.mkdirSync(output, { recursive: true });
  for (const file of index.corpus) {
    const target = path.join(output, 'corpus', file.path);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(source, file.path), target, fs.constants.COPYFILE_EXCL);
  }
  fs.writeFileSync(path.join(output, 'corpus-manifest.json'), JSON.stringify({ schema: 1, files: index.corpus }, null, 2) + '\n');
  fs.writeFileSync(path.join(output, '.gitignore'), [
    '*.key', '*.pem', '*.pub', '*readonly*', '.env*', '.venv/', 'venv/',
    'node_modules/', 'converter/', 'models/', '/*.zip', '/*.7z', '__pycache__/', '',
  ].join('\n'));
  fs.writeFileSync(path.join(output, 'README.md'), [
    '# Private SberAct verification corpus', '',
    'Keep this repository private. It contains real input documents for automated tests.',
    'corpus/ contains the original relative paths; corpus-manifest.json records SHA-256 and sizes.',
    'Only verification inputs belong here. Do not add SSH keys, OCR, models, Python environments or outputs.',
    'The public SberAct workflow must pin a specific commit and verify the corpus fingerprint.',
    'Do not publish corpus files or raw test output as public Actions artifacts.', '',
  ].join('\n'));
  await verify(output);
  console.log('Private corpus export prepared: ' + index.corpus.length + ' files; ' + output);
}
async function restore(directory) {
  assert.equal(process.env.GITHUB_ACTIONS, 'true', 'Restore is only allowed inside GitHub Actions');
  assert.equal(path.resolve(process.env.GITHUB_WORKSPACE), root, 'Unexpected Actions checkout');
  const files = await verify(directory);
  const target = path.join(root, 'Заявления');
  assert.ok(!fs.existsSync(target), 'Corpus target already exists');
  for (const file of files) {
    const output = path.join(target, file.path);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.copyFileSync(path.join(directory, 'corpus', file.path), output, fs.constants.COPYFILE_EXCL);
  }
  console.log('Private corpus verified and restored: ' + files.length + ' files');
}
module.exports = { verify };
if (require.main === module) {
  const [command, directory] = process.argv.slice(2);
  const home = path.resolve(process.env.SBERACT_CI_HOME || 'C:/Диск D/Сбер/SberAct-CI');
  const action = command === 'prepare' ? prepare(home)
    : command === 'verify' && directory ? verify(path.resolve(directory)).then(files => console.log('Private corpus verified: ' + files.length + ' files'))
    : command === 'restore' && directory ? restore(path.resolve(directory))
    : Promise.reject(new Error('Usage: node scripts/ci/corpus.js prepare|verify <directory>|restore <directory>'));
  action.catch(error => {
    const message = process.env.GITHUB_ACTIONS === 'true' && command === 'restore'
      ? 'Private corpus verification failed; check the pinned repository, commit and deploy key.'
      : error.message;
    console.error(message);
    process.exitCode = 1;
  });
}
