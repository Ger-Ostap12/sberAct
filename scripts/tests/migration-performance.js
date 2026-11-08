const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'sberact-copy-benchmark-'));
const run=(script,local)=> {
  const started=Date.now();
  const result=spawnSync('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',script,'-Mode','Prepare',
    '-Source',path.join(work,'legacy'),'-Target',path.join(local,'Programs/SberAct'),'-AppExe','SberAct Document Generator.exe'],
    {encoding:'utf8',windowsHide:true,env:{...process.env,LOCALAPPDATA:local}});
  assert.equal(result.status,0,result.stdout+result.stderr);
  assert.match(result.stdout,/verified|100%/i);
  return {seconds:(Date.now()-started)/1000,output:result.stdout};
};
try {
  const legacy=path.join(work,'legacy');
  const directory=path.join(legacy,'resources/converter/packages');
  fs.mkdirSync(directory,{recursive:true});
  fs.writeFileSync(path.join(legacy,'Uninstall SberAct Document Generator.exe'),'never executed');
  for(let i=0;i<1000;i++) {
    const folder=path.join(directory,'group'+Math.floor(i/20));
    fs.mkdirSync(folder,{recursive:true});
    fs.writeFileSync(path.join(folder,'module'+i+'.py'),'fixture '.repeat(64));
  }
  const before=spawnSync('git',['show','45bd974:scripts/migrate-install.ps1'],{cwd:root,encoding:'utf8'});
  assert.equal(before.status,0,before.stderr);
  const previous=path.join(work,'previous.ps1');
  fs.writeFileSync(previous,before.stdout);
  const old=run(previous,path.join(work,'old-data'));
  const current=run(path.join(root,'scripts/migrate-install.ps1'),path.join(work,'new-data'));
  assert.equal(fs.readdirSync(path.join(work,'new-data/Programs/SberAct/resources/converter/packages/group49')).length,20);
  const result={files:1000,bytes:1000*Buffer.byteLength('fixture '.repeat(64)),previousSeconds:old.seconds,currentSeconds:current.seconds,ratio:old.seconds/current.seconds};
  console.log(JSON.stringify(result,null,2));
  fs.mkdirSync(path.join(root,'temp/offline-update-build'),{recursive:true});
  fs.writeFileSync(path.join(root,'temp/offline-update-build/copy-benchmark.json'),JSON.stringify(result,null,2));
} finally {
  const full=fs.realpathSync(work);
  assert.equal(path.dirname(full).toLowerCase(),fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-copy-benchmark-'));
  fs.rmSync(full,{recursive:true,force:true});
}
