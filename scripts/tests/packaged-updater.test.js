const fs=require('node:fs');
const path=require('node:path');
const cp=require('node:child_process');
const assert=require('node:assert/strict');
const asar=require('@electron/asar');
const directory=path.resolve(process.argv[2] || 'temp/offline-update-build/win-unpacked');
const code="require('./resources/app.asar/electron-app/update-package.js');require('./resources/app.asar/electron-app/converter-update.js');require('./resources/app.asar/node_modules/electron-updater');console.log('Packaged update modules loaded')";
const result=cp.spawnSync(path.join(directory,'SberAct Document Generator.exe'),['-e',code],{
  cwd:directory,env:{...process.env,ELECTRON_RUN_AS_NODE:'1'},encoding:'utf8',windowsHide:true
});
process.stdout.write(result.stdout || '');
process.stderr.write(result.stderr || '');
assert.equal(result.status,0,'Update dependencies must load inside packaged Electron');
const archive=path.join(directory,'resources/app.asar');
for(const name of ['main.js','updater.js','update-package.js','converter-update.js']) {
  assert.ok(asar.extractFile(archive,path.join('electron-app',name)).equals(fs.readFileSync(path.join('electron-app',name))),name+' differs from current source');
}
assert.ok(asar.extractFile(archive,path.join('electron-app','build','asset-manifest.json')).equals(fs.readFileSync('electron-app/build/asset-manifest.json')));
const tool=path.join(directory,'resources/update-tools/converter-transaction.ps1');
assert.ok(fs.readFileSync(tool).equals(fs.readFileSync('scripts/converter-transaction.ps1')));
console.log('Packaged update modules, frontend and recovery tool match current source.');
