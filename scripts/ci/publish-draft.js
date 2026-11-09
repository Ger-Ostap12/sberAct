const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { digest, inspectPackage } = require('../../electron-app/update-package');
const { validate } = require('./ocr-component');

function assertDraft(release, sha) {
  assert.ok(release.draft && release.target_commitish === sha && release.body?.includes('SberAct CI commit: ' + sha),
    'Release already exists; published releases and drafts from another commit are not overwritten');
}
async function collectAssets(directory, pkg, component) {
  validate(component);
  const names = [
    pkg.installer, pkg.installer + '.blockmap', 'latest.yml', 'update-package.json',
    'converter-manifest.json', 'ocr-assets.json', 'Assemble-Update.ps1', 'build-info.json',
    'SberAct-App-Update-' + pkg.version + '.zip',
  ];
  const records = [];
  for (const name of names) {
    assert.match(name, /^[\w.-]+$/);
    const file = path.join(directory, name);
    records.push({ name, file, size: fs.statSync(file).size, sha256: await digest(file) });
  }
  let offset = 0;
  const archive = path.join(directory, component.archive.name);
  assert.equal(fs.statSync(archive).size, component.archive.size);
  for (const part of component.parts) {
    records.push({ ...part, file: archive, start: offset, end: offset + part.size - 1 });
    offset += part.size;
  }
  const sums = records.map(record => record.sha256 + '  ' + record.name).join('\n') + '\n';
  const file = path.join(directory, 'SHA256SUMS');
  fs.writeFileSync(file, sums);
  records.push({ name: 'SHA256SUMS', file, size: fs.statSync(file).size, sha256: await digest(file) });
  for (const record of records) assert.ok(record.size < 2 * 1024 ** 3, 'Release asset exceeds GitHub limit');
  return records;
}
async function main() {
  assert.equal(process.env.GITHUB_ACTIONS, 'true');
  assert.equal(process.env.GITHUB_REF, 'refs/heads/main');
  const sha = process.env.GITHUB_SHA;
  assert.match(sha, /^[a-f0-9]{40}$/);
  const directory = path.resolve(process.argv[2]);
  const pkg = await inspectPackage(directory);
  assert.ok(pkg.converter, 'A complete OCR package is required');
  const component = require('./ocr-assets.json');
  assert.equal(pkg.converter.version, component.version);
  const metadata = JSON.parse(fs.readFileSync(path.join(directory, 'update-package.json'), 'utf8'));
  assert.equal(metadata.files.find(file => file.path === 'converter.zip').sha256, component.archive.sha256);
  const records = await collectAssets(directory, pkg, component);
  const api = 'https://api.github.com/repos/' + process.env.GITHUB_REPOSITORY;
  const headers = { Authorization: 'Bearer ' + process.env.GITHUB_TOKEN, Accept: 'application/vnd.github+json' };
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { ...headers, ...options.headers } });
    if (!response.ok) throw new Error('GitHub Release request failed: HTTP ' + response.status);
    return response.status === 204 ? null : response.json();
  }
  const tag = 'v' + pkg.version;
  const marker = 'SberAct CI commit: ' + sha;
  const lookup = await fetch(api + '/releases/tags/' + encodeURIComponent(tag), { headers });
  let release;
  if (lookup.status === 404) {
    const ref = await fetch(api + '/git/ref/tags/' + encodeURIComponent(tag), { headers });
    if (ref.ok) {
      let object = (await ref.json()).object;
      for (let depth = 0; object.type === 'tag' && depth < 8; depth++) object = (await request(api + '/git/tags/' + object.sha)).object;
      assert.ok(object.type === 'commit' && object.sha === sha, 'Existing tag points to another commit');
    } else assert.equal(ref.status, 404, 'Cannot check release tag');
    release = await request(api + '/releases', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tag_name: tag, target_commitish: sha, name: 'SberAct ' + pkg.version, draft: true,
        body: marker + '\n\nApplication update: download SberAct-App-Update-' + pkg.version +
          '.zip, extract it and select the extracted folder in SberAct. Installed OCR is preserved.\n\n' +
          'First installation or OCR replacement: download the installer, feed, manifests, OCR parts and Assemble-Update.ps1 into one folder. Run the script to join and verify the full offline package.\n\nThe release remains a draft until manual verification.',
      }),
    });
  } else {
    if (!lookup.ok) throw new Error('Cannot inspect existing release: HTTP ' + lookup.status);
    release = await lookup.json();
    assertDraft(release, sha);
  }
  for (const record of records) {
    const existing = release.assets.find(asset => asset.name === record.name);
    if (existing?.label === 'sha256:' + record.sha256 && existing.size === record.size) continue;
    if (existing) await request(api + '/releases/assets/' + existing.id, { method: 'DELETE' });
    const url = release.upload_url.replace(/\{.*$/, '') + '?name=' + encodeURIComponent(record.name) + '&label=' + encodeURIComponent('sha256:' + record.sha256);
    const streamOptions = record.start === undefined ? {} : { start: record.start, end: record.end };
    await request(url, {
      method: 'POST', duplex: 'half',
      headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': String(record.size) },
      body: fs.createReadStream(record.file, streamOptions),
    });
    console.log('Uploaded draft asset: ' + record.name);
  }
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, 'Verified full release saved as a draft: ' + release.html_url + '\n');
}
module.exports = { assertDraft, collectAssets };
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
