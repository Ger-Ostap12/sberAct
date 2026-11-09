const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { test } = require('node:test');
const { spawnSync } = require('node:child_process');
const { split, join, validate } = require('../ci/ocr-component');
const root = path.resolve(__dirname, '../..');
function fixture() { return fs.mkdtempSync(path.join(os.tmpdir(), 'sberact-cloud-test-')); }
function cleanup(dir) {
  const full = fs.realpathSync(dir);
  assert.equal(path.dirname(full).toLowerCase(), fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-cloud-test-'));
  fs.rmSync(full, { recursive: true, force: true });
}
async function component(dir) {
  const original = path.join(dir, 'source.zip');
  fs.writeFileSync(original, 'archive-fixture-with-several-parts');
  const partsDir = path.join(dir, 'parts');
  return { partsDir, descriptor: {
    repository: 'owner/repo', tag: 'ci-ocr-fixture', version: 'fixture', launcherTextSha256: 'b'.repeat(64),
    ...await split(original, partsDir, 9),
    manifest: { name: 'converter-manifest.json', size: 1, sha256: 'a'.repeat(64) },
  } };
}
test('OCR parts round-trip without loading an archive into memory', async () => {
  const dir = fixture();
  try {
    const { partsDir, descriptor } = await component(dir);
    const output = path.join(dir, 'result.zip');
    await join(partsDir, descriptor, output);
    assert.deepEqual(fs.readFileSync(output), fs.readFileSync(path.join(dir, 'source.zip')));
    const second = path.join(dir, 'second.zip');
    fs.writeFileSync(path.join(partsDir, descriptor.parts[0].name), 'XXXXXXXXX');
    await assert.rejects(join(partsDir, descriptor, second), /checksum mismatch/);
    const reordered = { ...descriptor, parts: [...descriptor.parts].reverse() };
    assert.throws(() => validate(reordered));
    assert.throws(() => validate({ ...descriptor, parts: [{ ...descriptor.parts[0], size: 2 * 1024 ** 3 }] }));
  } finally { cleanup(dir); }
});
test('offline PowerShell assembler validates the same parts and metadata', async () => {
  if (process.platform !== 'win32') return;
  const dir = fixture();
  try {
    const { partsDir, descriptor } = await component(dir);
    fs.writeFileSync(path.join(partsDir, 'ocr-assets.json'), JSON.stringify(descriptor));
    fs.writeFileSync(path.join(partsDir, 'update-package.json'), JSON.stringify({
      schema: 1, converter: { archive: 'converter.zip', version: 'fixture' },
      files: [{ path: 'converter.zip', size: descriptor.archive.size, sha256: descriptor.archive.sha256 }],
    }));
    const run = () => spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'scripts/Assemble-Update.ps1'), '-Directory', partsDir], { encoding: 'utf8', windowsHide: true });
    let result = run();
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.deepEqual(fs.readFileSync(path.join(partsDir, 'converter.zip')), fs.readFileSync(path.join(dir, 'source.zip')));
    fs.writeFileSync(path.join(partsDir, 'converter.zip'), 'damaged');
    result = run();
    assert.notEqual(result.status, 0);
  } finally { cleanup(dir); }
});
test('private backend wrapper hides stdout, stderr and failure details but preserves failure', () => {
  const dir = fixture();
  try {
    const python = fs.existsSync(path.join(root, 'python-backend/venv/Scripts/python.exe'))
      ? path.join(root, 'python-backend/venv/Scripts/python.exe') : 'python';
    const script = [
      'import importlib.util,pathlib,sys,json',
      'spec=importlib.util.spec_from_file_location("private_ci",sys.argv[1])',
      'm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)',
      'folder=pathlib.Path(sys.argv[2])',
      'report=folder/"report.xml"',
      'xml=\'<testsuites><testsuite><testcase><failure message="PRIVATE_INPUT">PRIVATE_BODY</failure></testcase><testcase/></testsuite></testsuites>\'',
      'child="import pathlib,sys;print(\\"PRIVATE_STDOUT\\");print(\\"PRIVATE_STDERR\\",file=sys.stderr);pathlib.Path(sys.argv[1]).write_text(sys.argv[2]);sys.exit(1)"',
      'code=m.execute([sys.executable,"-c",child,str(report),xml],report,folder/"private.log")',
      'assert code==1',
      'assert "PRIVATE_STDOUT" in (folder/"private.log").read_text()',
    ].join('\n');
    const result = spawnSync(python, ['-c', script, path.join(root, 'scripts/ci/private-tests.py'), dir], { encoding: 'utf8', windowsHide: true });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /1 passed, 1 failed/);
    assert.doesNotMatch(result.stdout + result.stderr, /PRIVATE_(INPUT|BODY|STDOUT|STDERR)/);
  } finally { cleanup(dir); }
});

test('streamed OCR join fetches one part at a time and removes consumed parts', async () => {
  const dir = fixture();
  try {
    const { partsDir, descriptor } = await component(dir);
    const target = path.join(dir, 'streamed');
    fs.mkdirSync(target);
    await join(target, descriptor, path.join(target, 'converter.zip'), {
      fetchPart: async (part, file) => fs.copyFileSync(path.join(partsDir, part.name), file, fs.constants.COPYFILE_EXCL),
      removeParts: true,
    });
    assert.deepEqual(fs.readdirSync(target), ['converter.zip']);
    assert.deepEqual(fs.readFileSync(path.join(target, 'converter.zip')), fs.readFileSync(path.join(dir, 'source.zip')));
  } finally { cleanup(dir); }
});
test('draft publication rejects published releases and a different source commit', () => {
  const { assertDraft } = require('../ci/publish-draft');
  const sha = 'a'.repeat(40);
  const valid = { draft: true, target_commitish: sha, body: 'SberAct CI commit: ' + sha };
  assert.doesNotThrow(() => assertDraft(valid, sha));
  assert.throws(() => assertDraft({ ...valid, draft: false }, sha));
  assert.throws(() => assertDraft({ ...valid, target_commitish: 'b'.repeat(40) }, sha));
  assert.throws(() => assertDraft({ ...valid, body: 'manual draft' }, sha));
});
test('application-only archive excludes OCR and preserves its independent metadata', () => {
  if (process.platform !== 'win32') return;
  const dir = fixture();
  try {
    const app = path.join(dir, 'app');
    fs.mkdirSync(app);
    const metadata = { schema: 1, version: '2.1.3', converter: null, files: [] };
    fs.writeFileSync(path.join(app, 'update-package.json'), JSON.stringify(metadata));
    fs.writeFileSync(path.join(app, 'SberAct-Setup-2.1.3.exe'), 'installer fixture');
    const zip = path.join(dir, 'app.zip');
    const result = spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
      path.join(root, 'scripts/ci/pack-application.ps1'), '-SourceDir', app, '-Destination', zip],
    { encoding: 'utf8', windowsHide: true });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.ok(fs.statSync(zip).size > 0);
    const check = path.join(dir, 'check.ps1');
    fs.writeFileSync(check, [
      'param([string]$Zip)',
      "$ErrorActionPreference = 'Stop'",
      'Add-Type -AssemblyName System.IO.Compression.FileSystem',
      '$archive = [IO.Compression.ZipFile]::OpenRead($Zip)',
      'try {',
      'if ($archive.Entries.Count -ne 2) { throw "Unexpected files" }',
      '$entry = $archive.GetEntry("update-package.json")',
      'if (-not $entry) { throw "Missing package metadata" }',
      '$reader = [IO.StreamReader]::new($entry.Open())',
      'try { $data = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }',
      'if ($null -ne $data.converter) { throw "OCR must not be included" }',
      '} finally { $archive.Dispose() }',
    ].join('\n'));
    const checked = spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', check, '-Zip', zip], { encoding: 'utf8', windowsHide: true });
    assert.equal(checked.status, 0, checked.stdout + checked.stderr);
    fs.writeFileSync(path.join(app, 'converter.zip'), 'should be rejected');
    const bad = spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
      path.join(root, 'scripts/ci/pack-application.ps1'), '-SourceDir', app, '-Destination', path.join(dir, 'bad.zip')],
    { encoding: 'utf8', windowsHide: true });
    assert.notEqual(bad.status, 0);
    assert.equal(fs.existsSync(path.join(dir, 'bad.zip')), false);
  } finally { cleanup(dir); }
});

test('draft asset records publish OCR ranges without creating duplicate chunk files', async () => {
  const { collectAssets } = require('../ci/publish-draft');
  const dir = fixture();
  try {
    const { descriptor } = await component(dir);
    const pkg = { installer: 'SberAct-Setup-2.1.3.exe', version: '2.1.3' };
    for (const name of [pkg.installer, pkg.installer + '.blockmap', 'latest.yml', 'update-package.json',
      'converter-manifest.json', 'ocr-assets.json', 'Assemble-Update.ps1', 'build-info.json', 'SberAct-App-Update-2.1.3.zip']) {
      fs.writeFileSync(path.join(dir, name), 'fixture ' + name);
    }
    fs.copyFileSync(path.join(dir, 'source.zip'), path.join(dir, 'converter.zip'));
    const records = await collectAssets(dir, pkg, descriptor);
    assert.equal(records.some(record => record.name === 'converter.zip'), false);
    assert.ok(records.some(record => record.name === 'SberAct-App-Update-2.1.3.zip'));
    const bytes = fs.readFileSync(path.join(dir, 'converter.zip'));
    for (const part of descriptor.parts) {
      const record = records.find(record => record.name === part.name);
      const chunk = bytes.subarray(record.start, record.end + 1);
      assert.equal(chunk.length, record.size);
      assert.equal(crypto.createHash('sha256').update(chunk).digest('hex'), record.sha256);
      assert.equal(fs.existsSync(path.join(dir, part.name)), false);
    }
  } finally { cleanup(dir); }
});

test('private restore errors hide source paths in public Actions output', () => {
  const dir = fixture();
  try {
    const result = spawnSync(process.execPath, [path.join(root, 'scripts/ci/corpus.js'), 'restore', path.join(dir, 'PRIVATE_PERSON')], {
      encoding: 'utf8', env: { ...process.env, GITHUB_ACTIONS: 'true', GITHUB_WORKSPACE: root },
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Private corpus verification failed/);
    assert.doesNotMatch(result.stderr, /PRIVATE_PERSON/);
  } finally { cleanup(dir); }
});
test('private backend wrapper refuses all-skipped and empty reports', () => {
  const dir = fixture();
  try {
    const python = fs.existsSync(path.join(root, 'python-backend/venv/Scripts/python.exe'))
      ? path.join(root, 'python-backend/venv/Scripts/python.exe') : 'python';
    const script = [
      'import importlib.util,pathlib,sys',
      'spec=importlib.util.spec_from_file_location("private_ci",sys.argv[1])',
      'm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)',
      'folder=pathlib.Path(sys.argv[2])',
      'child="import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2]);print(\\"PRIVATE_ZERO\\")"',
      'for i,xml in enumerate(["<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>","<testsuites/>"]):',
      ' report=folder/("report"+str(i)+".xml")',
      ' assert m.execute([sys.executable,"-c",child,str(report),xml],report,folder/("log"+str(i)))!=0',
    ].join('\n');
    const result = spawnSync(python, ['-c', script, path.join(root, 'scripts/ci/private-tests.py'), dir], { encoding: 'utf8', windowsHide: true });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.doesNotMatch(result.stdout + result.stderr, /PRIVATE_ZERO/);
  } finally { cleanup(dir); }
});


test('release assets replace legacy SHA labels without reupload and only reuse verified content', async () => {
  const { reuseAsset } = require('../ci/publish-draft');
  const record = { name: 'SberAct-App-Update-2.1.3.zip', size: 123, sha256: 'a'.repeat(64) };
  const legacy = { id: 7, name: record.name, size: record.size, label: 'sha256:' + record.sha256 };
  const updates = [];
  const update = async (id, fields) => updates.push({ id, ...fields });
  assert.equal(await reuseAsset(legacy, record, update), true);
  assert.deepEqual(updates, [{ id: 7, name: record.name, label: record.name }]);
  updates.length = 0;
  const modern = { ...legacy, label: record.name, digest: 'sha256:' + record.sha256 };
  assert.equal(await reuseAsset(modern, record, update), true);
  assert.deepEqual(updates, []);
  for (const changed of [
    { ...modern, digest: 'sha256:' + 'b'.repeat(64) },
    { ...modern, size: record.size + 1 },
    { ...modern, name: 'another.zip' },
    { ...modern, digest: undefined },
  ]) assert.equal(await reuseAsset(changed, record, update), false);
  assert.deepEqual(updates, []);
});
