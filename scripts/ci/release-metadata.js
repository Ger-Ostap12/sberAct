const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const semver = require('semver');

function validate(root, baseVersion = null) {
  const read = name => JSON.parse(fs.readFileSync(path.join(root, name), 'utf8'));
  const app = read('package.json');
  assert.equal(semver.valid(app.version), app.version, 'Invalid application version');
  for (const prefix of ['', 'electron-app/']) {
    const pkg = read(prefix + 'package.json');
    const lock = read(prefix + 'package-lock.json');
    assert.equal(pkg.version, app.version, prefix + 'package.json version differs');
    assert.equal(lock.version, app.version, prefix + 'package-lock.json version differs');
    assert.equal(lock.packages[''].version, app.version, prefix + 'lock root version differs');
    for (const key of ['dependencies', 'devDependencies', 'optionalDependencies']) {
      assert.deepEqual(lock.packages[''][key], pkg[key], prefix + key + ' differs from lock');
    }
  }
  const changelog = fs.readFileSync(path.join(root, 'CHANGELOG.md'), 'utf8');
  const escaped = app.version.replace(/[.*+?^$()|[\]\\]/g, '\\$&');
  assert.match(changelog, new RegExp('^## ' + escaped + ' — \\d{2}\\.\\d{2}\\.\\d{4}\\r?\\n(?:\\r?\\n)*- .+', 'm'), 'Missing release notes for ' + app.version);
  if (baseVersion) assert.ok(semver.gt(app.version, baseVersion), 'Release version must exceed main version ' + baseVersion);
  return app.version;
}

async function main() {
  let baseVersion = null;
  if (process.env.GITHUB_EVENT_NAME === 'pull_request') {
    const event = JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
    if (event.pull_request.base.ref === 'main') {
      assert.equal(event.pull_request.head.ref, 'release', 'Only release may target main');
      const repository = process.env.GITHUB_REPOSITORY;
      const sha = event.pull_request.base.sha;
      const response = await fetch('https://api.github.com/repos/' + repository + '/contents/package.json?ref=' + encodeURIComponent(sha), {
        headers: { Authorization: 'Bearer ' + process.env.GITHUB_TOKEN, Accept: 'application/vnd.github+json' },
      });
      assert.ok(response.ok, 'Cannot read main version: HTTP ' + response.status);
      const file = await response.json();
      baseVersion = JSON.parse(Buffer.from(file.content, 'base64').toString('utf8')).version;
    }
  }
  console.log('Release metadata verified: ' + validate(process.cwd(), baseVersion));
}
module.exports = { validate };
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
