const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const upstream = path.join(root, 'node_modules/app-builder-lib/templates/nsis');
const read = (name) => fs.readFileSync(path.join(root, name), 'utf8').replace(/\r\n/g, '\n');
const config = require('../../package.json');
assert.equal(config.build.nsis.allowToChangeInstallationDirectory, false);
assert.equal(config.build.nsis.perMachine, false);
assert.equal(config.build.nsis.script, 'scripts/installer.nsi');
assert.equal(require('app-builder-lib/package.json').version, '24.13.3', 'Review vendored NSIS templates when upgrading electron-builder');
let expected = fs.readFileSync(path.join(upstream, 'installer.nsi'), 'utf8').replace(/\r\n/g, '\n');
expected = expected.replace('!insertmacro initMultiUser', '!insertmacro sberactInitMultiUser').replace('!include "multiUser.nsh"', '!include "multiUser.nsh"\n!include "${PROJECT_DIR}\\scripts\\install-policy.nsh"')
  .replace('!include "installSection.nsh"', '!include "${PROJECT_DIR}\\scripts\\install-section.nsh"')
  .replace('!ifdef BUILD_UNINSTALLER\n  !include "uninstaller.nsh"\n!endif', '!define BUILD_UNINSTALLER\nFunction un._GetProcessInfo\n  !insertmacro FUNC_GETPROCESSINFO\nFunctionEnd\nUninstPage instfiles\n!include "uninstaller.nsh"\n!undef BUILD_UNINSTALLER');
assert.equal(read('scripts/installer.nsi').split('\n').slice(1).join('\n'), expected);
const section = read('scripts/install-section.nsh');
assert.ok(section.indexOf('!insertmacro sberactPrepareMigration') < section.indexOf('!insertmacro uninstallOldVersion'));
assert.ok(section.indexOf('!insertmacro customInstall') < section.indexOf('!insertmacro sberactRetireLegacy'));
assert.ok(section.indexOf('!insertmacro sberactRetireLegacy') < section.indexOf('!insertmacro registryAddInstallInfo'));
if (process.platform !== 'win32') {
  console.log('Installer contracts passed; Windows migration checks skipped.');
  process.exit(0);
}
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'sberact-installer-test-'));
try {
  const legacy = path.join(work, 'old app');
  const target = path.join(work, 'Programs/SberAct');
  const exe = 'SberAct Document Generator.exe';
  const write = (relative, content) => {
    const file = path.join(legacy, relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  };
  write('Uninstall ' + exe, 'test fixture, never executed');
  write(exe, 'old application');
  write('resources/converter/pyruntime/python.exe', 'python fixture');
  write('resources/converter/nested/[Content_Types].xml', 'keep brackets');
  write('generated/act.docx', 'original document');
  const run = (overrides = {}) => spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'scripts/migrate-install.ps1'),
    '-Mode', overrides.mode || 'Prepare', '-Source', legacy, '-Target', overrides.target || target, '-AppExe', exe],
    { encoding: 'utf8', env: { ...process.env, LOCALAPPDATA: work }, windowsHide: true });
  let result = run();
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(fs.readFileSync(path.join(target, 'resources/converter/nested/[Content_Types].xml'), 'utf8'), 'keep brackets');
  assert.equal(fs.readFileSync(path.join(legacy, 'generated/act.docx'), 'utf8'), 'original document');
  const backupRoot = path.join(work, 'SberAct/migration-backups');
  const backup = fs.readdirSync(backupRoot)[0];
  assert.equal(fs.readFileSync(path.join(backupRoot, backup, 'generated/act.docx'), 'utf8'), 'original document');
  result = run({ target: path.join(work, 'unexpected') });
  assert.notEqual(result.status, 0, 'Reject arbitrary target directory');
  result = run({ mode: 'Retire' });
  assert.notEqual(result.status, 0, 'Incomplete new installation must not execute old uninstaller');
  assert.equal(fs.readFileSync(path.join(legacy, exe), 'utf8'), 'old application');
  const compiler = path.join(process.env.LOCALAPPDATA, 'electron-builder/Cache/nsis/nsis-3.0.4.1/Bin/makensis.exe');
  assert.ok(fs.existsSync(compiler), 'Install cached NSIS compiler before running Windows migration checks');
  const fixtureScript = path.join(work, 'legacy-uninstaller.nsi');
  fs.writeFileSync(fixtureScript, `Unicode true\nOutFile "${path.join(legacy, 'Uninstall ' + exe)}"\nSilentInstall silent\nRequestExecutionLevel user\nSection\nDelete "$EXEDIR\\${exe}"\nSectionEnd\n`);
  result = spawnSync(compiler, ['/V2', fixtureScript], { encoding: 'utf8', windowsHide: true });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  for (const relative of [exe, 'resources/app.asar', 'resources/backend/SberAct.exe']) {
    const file = path.join(target, relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, 'new application fixture');
  }
  for (const relative of ['docling_dev/api.py', 'vendor/tesseract/tesseract.exe']) {
    const file = path.join(target, 'resources/converter', relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, 'converter fixture');
  }
  result = run({ mode: 'Retire' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.equal(fs.existsSync(path.join(legacy, exe)), false, 'Legacy fixture retired');
  assert.equal(fs.readFileSync(path.join(target, exe), 'utf8'), 'new application fixture');
  assert.equal(fs.readFileSync(path.join(legacy, 'resources/converter/pyruntime/python.exe'), 'utf8'), 'python fixture');
  console.log('Installer contracts and migration checks passed (including a real fixture executable).');
} finally {
  const resolved = fs.realpathSync(work);
  assert.equal(path.dirname(resolved).toLowerCase(), fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(resolved).startsWith('sberact-installer-test-'));
  fs.rmSync(resolved, { recursive: true, force: true });
}
