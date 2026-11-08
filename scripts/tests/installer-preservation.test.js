const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'sberact-nsis-preserve-'));
function put(relative,text) {const file=path.join(work,'app',relative);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,text);}
try {
  put('resources/converter/main.py','active converter');
  put('resources/.converter-previous/main.py','previous converter');
  put('resources/.converter-next/main.py','prepared converter');
  put('resources/.converter-update.json','journal fixture');
  put('resources/backend/old.dll','must be removed');
  const exe=path.join(work,'preserve.exe');
  const script=path.join(work,'preserve.nsi');
  fs.writeFileSync(script,[
    'Unicode true','SilentInstall silent','RequestExecutionLevel user',
    'OutFile "'+exe+'"','!include "LogicLib.nsh"','!include "FileFunc.nsh"',
    '!define PROJECT_DIR "'+root+'"',"!define isUpdated '1 == 1'",
    '!include "'+path.join(root,'scripts/installer.nsh')+'"',
    'Section','StrCpy $INSTDIR "'+path.join(work,'app')+'"','!insertmacro customRemoveFiles','SectionEnd'
  ].join('\n'));
  const compiler=path.join(process.env.LOCALAPPDATA,'electron-builder/Cache/nsis/nsis-3.0.4.1/Bin/makensis.exe');
  let result=spawnSync(compiler,['/V2','-INPUTCHARSET','UTF8',script],{encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stdout+result.stderr);
  result=spawnSync(exe,['/S'],{encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stdout+result.stderr);
  for(const [name,content] of Object.entries({
    'converter/main.py':'active converter','.converter-previous/main.py':'previous converter',
    '.converter-next/main.py':'prepared converter','.converter-update.json':'journal fixture'
  })) assert.equal(fs.readFileSync(path.join(work,'app/resources',name),'utf8'),content);
  assert.equal(fs.existsSync(path.join(work,'app/resources/backend/old.dll')),false);
  assert.equal(fs.existsSync(path.join(work,'app.converter-keep')),false);
  fs.mkdirSync(path.join(work,'app.converter-keep'));
  result=spawnSync(exe,['/S'],{encoding:'utf8',windowsHide:true});
  assert.notEqual(result.status,0);
  assert.equal(fs.readFileSync(path.join(work,'app/resources/converter/main.py'),'utf8'),'active converter');
  console.log('NSIS runtime checks passed: active, previous, prepared and journal survive app replacement; existing recovery directory aborts deletion.');
} finally {
  const full=fs.realpathSync(work);
  assert.equal(path.dirname(full).toLowerCase(),fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-nsis-preserve-'));
  fs.rmSync(full,{recursive:true,force:true});
}
