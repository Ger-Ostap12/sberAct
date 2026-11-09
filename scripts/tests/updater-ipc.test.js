const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const Module=require('node:module');
const yaml=require('js-yaml');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'sberact-update-ipc-'));
const handlers=new Map();
let downloads=0,installs=0,stops=0,version='2.1.0',phase=null;
const calls=[];
let failStop=false;
const events={};
const updater={on:(name,cb)=>{events[name]=cb;},setFeedURL:()=>{},checkForUpdates:async()=>({}),downloadUpdate:async()=>{downloads++;return[];},quitAndInstall:()=>{installs++;}};
const fakeConverter={
  state:async()=>phase,
  transaction:async(action,directory,options)=>{calls.push({action,directory,options});if(action==='Prepare')phase={phase:'prepared'};if(action==='Activate')phase={phase:'pending'};if(action==='Recover')phase=null;return 'Extracting converter: 2/10\nVerifying converter: 10/10\n{"prepared":true}\n';},
  stopConverter:async()=>{if(failStop)throw new Error("converter is still running");stops++;}
};
const electron={app:{isPackaged:true,getVersion:()=>version,relaunch:()=>{},quit:()=>{}},ipcMain:{handle:(name,cb)=>handlers.set(name,cb)},dialog:{}};
const originalLoad=Module._load;
Module._load=function(name,parent,...rest) {
  if(name==='electron') return electron;
  if(name==='electron-updater') return {autoUpdater:updater};
  if(name==='./converter-update' && parent.filename.endsWith(path.join('electron-app','updater.js'))) return fakeConverter;
  return originalLoad.call(this,name,parent,...rest);
};
const api=require('../../electron-app/updater');
const sha=body=>crypto.createHash('sha256').update(body).digest('hex');
function fixture() {
  const name='SberAct-Setup-2.1.2.exe';
  const installer=Buffer.from('installer fixture');
  const manifest=JSON.stringify({version:'converter-version',files:[{path:'main.py',size:4,sha256:sha('code')},{path:'pyruntime/python.exe',size:15,sha256:sha('runtime fixture')}]});
  const contents={
    [name]:installer,
    'latest.yml':yaml.dump({version:'2.1.2',files:[{url:name,size:installer.length,sha512:crypto.createHash('sha512').update(installer).digest('base64')}]}),
    'converter.zip':'fixture: extraction is tested separately',
    'converter-manifest.json':manifest
  };
  const files=[];
  for(const [name,body] of Object.entries(contents)) {
    fs.writeFileSync(path.join(work,name),body);
    files.push({path:name,size:Buffer.byteLength(body),sha256:sha(body)});
  }
  fs.writeFileSync(path.join(work,'update-package.json'),JSON.stringify({schema:1,version:'2.1.2',files,converter:{archive:'converter.zip',manifest:'converter-manifest.json',version:'converter-version',unpackedBytes:19}}));
}
async function invoke(name,options) {return handlers.get('update:'+name)({},options);}
async function main() {
  fixture();
  api.initUpdater({getMainWindow:()=>null,converterDir:path.join(work,'installed/converter'),backendPort:8000});
  let result=await invoke('apply',{appDownloaded:true,converterPlan:{toCopy:[{path:'../../outside'}]}});
  assert.equal(result.ok,false);assert.equal(calls.length,0);
  result=await invoke('check',work);assert.equal(result.ok,true,result.error);assert.equal(result.app.available,true);
  result=await invoke('apply',{appDownloaded:true});assert.equal(result.ok,false);assert.equal(calls.length,0);
  // getAutoUpdater is loaded lazily during check; the cached instance is reused.
  result=await invoke('download');assert.equal(result.ok,true,result.error);
  assert.equal(downloads,1);assert.equal(updater.disableDifferentialDownload,true);
  fs.appendFileSync(path.join(work,'converter.zip'),'broken');
  result=await invoke('apply',{appDownloaded:true});assert.equal(result.ok,false);assert.equal(stops,0);
  fixture();
  result=await invoke('check',work);assert.equal(result.ok,true,result.error);
  result=await invoke('download');assert.equal(result.ok,true,result.error);
  failStop=true;
  result=await invoke('apply',{appDownloaded:true});
  assert.equal(result.ok,false);
  assert.deepEqual(calls.map(c=>c.action),['Prepare','Recover']);
  calls.length=0;failStop=false;
  result=await invoke('apply',{appDownloaded:true,converterPlan:{flashManifestPath:'C:/outside',toCopy:[{path:'../../outside'}]}});
  assert.equal(result.ok,true,result.error);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(stops,1);assert.equal(installs,1);
  assert.deepEqual(calls.map(c=>c.action),['Prepare','Activate']);
  assert.equal(calls[0].options.zip,path.join(work,'converter.zip'));
  phase={phase:'pending'};
  result=await invoke('check',work);assert.equal(result.ok,false);
  phase=null;version='2.1.3';
  result=await invoke('check',work);assert.equal(result.ok,false);
  phase=null;version='2.1.0';
  fixture();
  let metadata=JSON.parse(fs.readFileSync(path.join(work,'update-package.json'),'utf8'));
  metadata.converter=null;
  metadata.files=metadata.files.filter(file=>!file.path.startsWith('converter'));
  fs.writeFileSync(path.join(work,'update-package.json'),JSON.stringify(metadata));
  fs.unlinkSync(path.join(work,'converter.zip'));
  fs.unlinkSync(path.join(work,'converter-manifest.json'));
  result=await invoke('check',work);
  assert.equal(result.ok,true,result.error);
  assert.equal(result.converter.status,'not_in_package');
  assert.equal(result.converter.installed,false);
  const installed=path.join(work,'installed/converter');
  fs.mkdirSync(path.join(installed,'pyruntime'),{recursive:true});
  fs.writeFileSync(path.join(installed,'main.py'),'code');
  fs.writeFileSync(path.join(installed,'pyruntime/python.exe'),'runtime fixture');
  result=await invoke('check',work);
  assert.equal(result.converter.status,'not_in_package');
  assert.equal(result.converter.installed,true);
  assert.equal(result.converter.installedVersion,null);
  fixture();
  assert.equal(fs.existsSync(path.join(installed,'converter-manifest.json')),false);
  result=await invoke('check',work);
  assert.equal(result.converter.status,'matches_package');
  assert.equal(result.converter.available,false);
  assert.equal(result.converter.manifestRecorded,true);
  assert.equal(result.converter.filesChanged,0);
  assert.equal(result.converter.filesMissing,0);
  assert.equal(fs.existsSync(path.join(installed,'converter-manifest.json')),true);
  fs.writeFileSync(path.join(installed,'main.py'),'Code');
  result=await invoke('check',work);
  assert.equal(result.converter.available,true);
  assert.equal(result.converter.filesChanged,1);
  assert.equal(result.converter.bytes,4);
  assert.equal(result.converter.replacementBytes,19);
  console.log('Updater IPC checks passed: stale input, damaged package, downloaded state, downgrade, pending update, server-owned plan.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  Module._load=originalLoad;
  api.shutdownUpdater();
  const full=fs.realpathSync(work);
  assert.equal(path.dirname(full).toLowerCase(),fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-update-ipc-'));
  fs.rmSync(full,{recursive:true,force:true});
});
