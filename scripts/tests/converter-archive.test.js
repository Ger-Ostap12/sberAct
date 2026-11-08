const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '../..');
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'sberact-archive-test-'));
const source = path.join(work, 'converter');
fs.mkdirSync(path.join(source, 'models/docling/nested'), { recursive: true });
const content = new Map([['main.py', 'converter fixture'], ['models/docling/nested/model.bin', 'model fixture']]);
for (const [name, text] of content) fs.writeFileSync(path.join(source, name), text);
for (let i = 0; i < 5; i++) fs.writeFileSync(path.join(source, 'models/docling/nested/model.bin.part00' + i), 'excluded part');
const manifest = path.join(source, 'converter-manifest.json');
fs.writeFileSync(manifest, JSON.stringify({ files: [...content].map(([name, text]) => ({
  path: name, size: Buffer.byteLength(text), sha256: crypto.createHash('sha256').update(text).digest('hex')
})) }));
const run = (script, args = []) => spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, ...args],
  { encoding: 'utf8', windowsHide: true });
const verify = zip => run(path.join(root, 'scripts/verify-converter-archive.ps1'), ['-Zip', zip, '-ManifestFile', manifest]);
try {
  const packed = path.join(work, 'valid.zip');
  let result = run(path.join(root, 'scripts/pack-converter.ps1'), ['-SourceDir', source, '-Zip', packed, '-ManifestFile', manifest]);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  result = verify(packed);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /Archive verified: 3 files/);

  const create = path.join(work, 'create.ps1');
  fs.writeFileSync(create, [
    'param([string]$Spec, [string]$Zip)',
    "$ErrorActionPreference = 'Stop'",
    'Add-Type -AssemblyName System.IO.Compression',
    'Add-Type -AssemblyName System.IO.Compression.FileSystem',
    '$archive = [IO.Compression.ZipFile]::Open($Zip, [IO.Compression.ZipArchiveMode]::Create)',
    'try { foreach ($item in (Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json)) {',
    '  $entry = $archive.CreateEntry($item.name)',
    '  $output = $entry.Open()',
    '  try { $bytes = [Convert]::FromBase64String($item.data); $output.Write($bytes, 0, $bytes.Length) } finally { $output.Dispose() }',
    '} } finally { $archive.Dispose() }'
  ].join('\n'));
  const entries = [...content, ['converter-manifest.json', fs.readFileSync(manifest, 'utf8')]]
    .map(([name, text]) => ({ name: 'converter/' + name, data: Buffer.from(text).toString('base64') }));
  const changed = text => Buffer.from(text).toString('base64');
  const cases = [
    ['missing', entries.slice(1), /Archive is incomplete/],
    ['unexpected', [...entries, { name: 'converter/extra.py', data: changed('extra') }], /Unexpected archive entry/],
    ['renamed-same-count', entries.map((e, i) => i === 0 ? { ...e, name: 'converter/renamed.py' } : e), /Unexpected archive entry/],
    ['duplicate', [...entries, entries[0]], /Duplicate archive entry/],
    ['wrong-size', entries.map((e, i) => i === 0 ? { ...e, data: changed('short') } : e), /Archive size mismatch/],
    ['wrong-hash', entries.map((e, i) => i === 0 ? { ...e, data: changed('Converter fixture') } : e), /Archive hash mismatch/],
    ['missing-manifest', entries.slice(0, -1), /Archive is incomplete/],
    ['changed-manifest', entries.map((e, i) => i === 2 ? { ...e, data: changed(fs.readFileSync(manifest, 'utf8').replace('files', 'Files')) } : e), /Archive hash mismatch/],
  ];
  for (const [name, items, message] of cases) {
    const spec = path.join(work, name + '.json');
    const zip = path.join(work, name + '.zip');
    fs.writeFileSync(spec, JSON.stringify(items));
    result = run(create, ['-Spec', spec, '-Zip', zip]);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    result = verify(zip);
    assert.notEqual(result.status, 0, name);
    assert.match(result.stdout + result.stderr, message, name);
  }
  console.log('Converter archive checks passed: excluded nested parts, missing/extra/renamed files, duplicates, sizes, hashes and embedded manifest.');
} finally {
  const full = fs.realpathSync(work);
  assert.equal(path.dirname(full).toLowerCase(), fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-archive-test-'));
  fs.rmSync(full, { recursive: true, force: true });
}
