const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { pipeline } = require('node:stream/promises');
const { Readable } = require('node:stream');
const { digest, inspectPackage, validateManifest } = require('../../electron-app/update-package');
const root = path.resolve(__dirname, '../..');

function validate(component) {
  assert.match(component.repository, /^[\w.-]+\/[\w.-]+$/);
  assert.match(component.tag, /^[\w.-]+$/);
  assert.ok(component.version && Array.isArray(component.parts) && component.parts.length);
  assert.match(component.launcherTextSha256, /^[a-f0-9]{64}$/);
  for (const file of [component.archive, component.manifest, ...component.parts]) {
    assert.match(file.name, /^[\w.-]+$/);
    assert.ok(Number.isSafeInteger(file.size) && file.size > 0);
    assert.match(file.sha256, /^[a-f0-9]{64}$/);
  }
  assert.equal(component.archive.name, 'converter.zip');
  assert.equal(component.manifest.name, 'converter-manifest.json');
  for (const [i, part] of component.parts.entries()) {
    assert.equal(part.name, 'converter.zip.part-' + String(i).padStart(3, '0'));
    assert.ok(part.size < 2 * 1024 ** 3);
  }
  assert.equal(component.parts.reduce((sum, part) => sum + part.size, 0), component.archive.size);
  return component;
}
async function split(source, destination, chunkSize = 1536 * 1024 ** 2) {
  assert.ok(Number.isSafeInteger(chunkSize) && chunkSize > 0 && chunkSize < 2 * 1024 ** 3);
  fs.mkdirSync(destination);
  const input = fs.openSync(source, 'r');
  const archiveHash = crypto.createHash('sha256');
  const parts = [];
  let total = 0;
  try {
    const buffer = Buffer.alloc(1024 * 1024);
    while (true) {
      const name = 'converter.zip.part-' + String(parts.length).padStart(3, '0');
      const full = path.join(destination, name);
      let output = null, size = 0;
      const hash = crypto.createHash('sha256');
      try {
        while (size < chunkSize) {
          const length = fs.readSync(input, buffer, 0, Math.min(buffer.length, chunkSize - size), null);
          if (!length) break;
          if (output === null) output = fs.openSync(full, 'wx');
          let written = 0;
          while (written < length) written += fs.writeSync(output, buffer, written, length - written);
          hash.update(buffer.subarray(0, length));
          archiveHash.update(buffer.subarray(0, length));
          size += length;
        }
      } finally { if (output !== null) fs.closeSync(output); }
      if (!size) break;
      parts.push({ name, size, sha256: hash.digest('hex') });
      total += size;
      console.log('Prepared OCR part: ' + parts.length);
    }
  } finally { fs.closeSync(input); }
  return { archive: { name: 'converter.zip', size: total, sha256: archiveHash.digest('hex') }, parts };
}
async function join(directory, component, destination, { fetchPart = null, removeParts = false } = {}) {
  validate(component);
  const output = fs.createWriteStream(destination, { flags: 'wx' });
  const hash = crypto.createHash('sha256');
  let size = 0;
  async function* chunks() {
    for (const part of component.parts) {
      const file = path.join(directory, part.name);
      if (fetchPart) await fetchPart(part, file);
      assert.equal(fs.statSync(file).size, part.size, 'OCR part size mismatch');
      assert.equal(await digest(file), part.sha256, 'OCR part checksum mismatch');
      for await (const bytes of fs.createReadStream(file)) { hash.update(bytes); size += bytes.length; yield bytes; }
      if (removeParts) fs.unlinkSync(file);
    }
  }
  await pipeline(Readable.from(chunks()), output);
  assert.equal(size, component.archive.size, 'OCR archive size mismatch');
  assert.equal(hash.digest('hex'), component.archive.sha256, 'OCR archive checksum mismatch');
}
async function download(component, file, destination) {
  const url = 'https://github.com/' + component.repository + '/releases/download/' + encodeURIComponent(component.tag) + '/' + encodeURIComponent(file.name);
  const response = await fetch(url);
  assert.ok(response.ok && response.body, 'Cannot download pinned OCR asset: HTTP ' + response.status);
  await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(destination, { flags: 'wx' }));
  assert.equal(fs.statSync(destination).size, file.size, 'Downloaded asset size mismatch');
  assert.equal(await digest(destination), file.sha256, 'Downloaded asset checksum mismatch');
}
async function prepare() {
  const source = path.join(root, 'release/SberAct-Update');
  const pkg = await inspectPackage(source);
  assert.ok(pkg.converter, 'A verified full local update package is required');
  const manifest = pkg.converter.manifestData;
  const home = path.resolve(process.env.SBERACT_CI_HOME || 'C:/Диск D/Сбер/SberAct-CI');
  const tag = 'ci-ocr-' + manifest.version;
  const output = path.join(home, 'exports', tag);
  assert.ok(!fs.existsSync(output), 'OCR export already exists; refusing to overwrite');
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const result = await split(path.join(source, 'converter.zip'), output);
  const name = 'converter-manifest.json';
  fs.copyFileSync(path.join(source, name), path.join(output, name), fs.constants.COPYFILE_EXCL);
  const launcher = manifest.files.find(file => file.path === 'run_converter.py');
  assert.ok(launcher && launcher.sha256 === await digest(path.join(root, 'python-backend/app/run_converter.py')), 'Source launcher differs from the verified archive');
  const launcherTextSha256 = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'python-backend/app/run_converter.py'), 'utf8').replace(/\r\n/g, '\n')).digest('hex');
  const component = validate({
    launcherTextSha256,
    repository: 'Ger-Ostap12/sberAct', tag, version: manifest.version,
    ...result, manifest: { name, size: fs.statSync(path.join(output, name)).size, sha256: await digest(path.join(output, name)) },
  });
  const json = JSON.stringify(component, null, 2) + '\n';
  fs.writeFileSync(path.join(output, 'ocr-assets.json'), json);
  fs.writeFileSync(path.join(__dirname, 'ocr-assets.json'), json);
  console.log('OCR export ready: ' + output);
}
async function compose(directory, component) {
  validate(component);
  const app = await inspectPackage(directory);
  assert.equal(app.converter, null, 'Expected an application-only intermediate package');
  await download(component, component.manifest, path.join(directory, component.manifest.name));
  const manifest = validateManifest(JSON.parse(fs.readFileSync(path.join(directory, component.manifest.name), 'utf8')));
  assert.equal(manifest.version, component.version);
  for (const prefix of ['pyruntime', '.venv/Lib/site-packages/torch/lib']) {
    for (const name of ['msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll']) {
      const file = manifest.files.find(file => file.path.toLowerCase() === (prefix + '/' + name).toLowerCase());
      assert.ok(file, 'Bundled runtime is absent from OCR');
      assert.equal(file.sha256, await digest(path.join(root, 'vendor/msvc-runtime', name)), 'OCR runtime differs; prepare a new OCR component');
    }
  }
  const launcher = manifest.files.find(file => file.path === 'run_converter.py');
  assert.ok(launcher);
  const launcherTextSha256 = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'python-backend/app/run_converter.py'), 'utf8').replace(/\r\n/g, '\n')).digest('hex');
  assert.equal(component.launcherTextSha256, launcherTextSha256, 'OCR launcher differs; prepare a new OCR component');
  await join(directory, component, path.join(directory, component.archive.name), {
    fetchPart: (part, file) => { console.log('Downloading pinned asset: ' + part.name); return download(component, part, file); },
    removeParts: true,
  });
  const files = [];
  for (const name of ['latest.yml', app.installer, app.installer + '.blockmap', component.manifest.name, component.archive.name]) {
    files.push({ path: name, size: fs.statSync(path.join(directory, name)).size, sha256: await digest(path.join(directory, name)) });
  }
  const metadata = {
    schema: 1, version: app.version,
    converter: { archive: component.archive.name, manifest: component.manifest.name, version: manifest.version, unpackedBytes: manifest.files.reduce((sum, file) => sum + file.size, 0) },
    files,
  };
  fs.writeFileSync(path.join(directory, 'update-package.json'), JSON.stringify(metadata, null, 2));
  await inspectPackage(directory);
  fs.writeFileSync(path.join(directory, 'ocr-assets.json'), JSON.stringify(component, null, 2));
  fs.copyFileSync(path.join(root, 'scripts/Assemble-Update.ps1'), path.join(directory, 'Assemble-Update.ps1'), fs.constants.COPYFILE_EXCL);
  fs.writeFileSync(path.join(directory, 'build-info.json'), JSON.stringify({
    version: app.version, commit: process.env.GITHUB_SHA, ocr: component.version,
    corpusCommit: require('./private-data.json').commit,
  }, null, 2));
  const smallName = 'SberAct-App-Update-' + app.version + '.zip';
  fs.renameSync(path.join(directory, '..', smallName), path.join(directory, smallName));
  console.log('Complete offline package assembled and verified: ' + app.version);
}
module.exports = { validate, split, join };
if (require.main === module) {
  const [command, directory] = process.argv.slice(2);
  const action = command === 'prepare' ? prepare()
    : command === 'compose' && directory && process.env.GITHUB_ACTIONS === 'true'
      ? compose(path.resolve(directory), require('./ocr-assets.json'))
      : Promise.reject(new Error('Use prepare, or compose <directory> inside GitHub Actions'));
  action.catch(error => { console.error(error.message); process.exitCode = 1; });
}
