const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const yaml = require('js-yaml');
const { buildUpdate } = require('../build-update');
const { inspectPackage, converterMatches } = require('../../electron-app/update-package');
const { finishPendingUpdate } = require('../../electron-app/converter-update');
const root=path.resolve(__dirname,'../..');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'sberact-update-test-'));
function write(file,content) { fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,content); }
function feed(release,version) {
  const name='SberAct-Setup-'+version+'.exe';
  const body=Buffer.from('installer fixture '+version);
  write(path.join(release,name),body);
  write(path.join(release,'latest.yml'),yaml.dump({version,files:[{url:name,size:body.length,sha512:crypto.createHash('sha512').update(body).digest('base64')}]}));
}
function run(action,dest,extra=[]) {
  return spawnSync('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(root,'scripts/converter-transaction.ps1'),'-Action',action,'-Dest',dest,...extra],
    {encoding:'utf8',windowsHide:true});
}
function ok(action,dest,extra) { const result=run(action,dest,extra);assert.equal(result.status,0,result.stdout+result.stderr);return result; }
function source(version) {
  const directory=path.join(work,'converter-'+version);
  for(const relative of ['main.py','run_converter.py','docling_dev/api.py','pyruntime/python.exe','vendor/tesseract/tesseract.exe','.venv/Lib/site-packages/module.py','models/docling/model.json','[Content_Types].xml']) write(path.join(directory,relative),'old '+relative);
  write(path.join(directory,'.gitignore'),'must not ship');
  write(path.join(directory,'pyruntime/vcruntime140.dll'),'old Python runtime');
  write(path.join(directory,'.venv/Lib/site-packages/torch/lib/torch_cpu.dll'),'torch fixture');
  return directory;
}
async function main() {
  const release=path.join(work,'release');fs.mkdirSync(release);
  const src=source('full');
  const runtimeDir=path.join(work,'runtime');
  for(const name of ['msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'])write(path.join(runtimeDir,name),'bundled '+name);
  const dest=path.join(work,'resources');
  ok('Install',dest,['-SourceDir',src]);
  ok('Confirm',dest);
  assert.notEqual(run('Check',dest,['-ReserveKB','2147483647']).status,0);
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
  console.log('ok: first installation, confirmation and insufficient-space preflight');
  feed(release,'2.1.1');
  write(path.join(src,'main.py'),'changed in 2.1.1');
  await buildUpdate({releaseDir:release,converterDir:src,runtimeDir,version:'2.1.1'});
  feed(release,'2.1.2');
  write(path.join(src,'docling_dev/api.py'),'changed in 2.1.2');
  const output=await buildUpdate({releaseDir:release,converterDir:src,runtimeDir,version:'2.1.2'});
  const pkg=await inspectPackage(output);
  assert.ok(!pkg.converter.manifestData.files.some(file=>file.path==='.gitignore'));
  assert.equal(await converterMatches(path.join(dest,'converter'),pkg.converter.manifestData),false);
  const options=['-Zip',path.join(output,'converter.zip'),'-ManifestFile',path.join(output,'converter-manifest.json')];
  ok('Check',dest,options);
  assert.equal(fs.existsSync(path.join(dest,'.converter-update.json')),false);
  ok('Prepare',dest,options);
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
  ok('Activate',dest);
  assert.equal(fs.readFileSync(path.join(dest,'converter/pyruntime/vcruntime140.dll'),'utf8'),'bundled vcruntime140.dll');
  assert.equal(fs.readFileSync(path.join(dest,'converter/.venv/Lib/site-packages/torch/lib/msvcp140.dll'),'utf8'),'bundled msvcp140.dll');
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'changed in 2.1.1');
  assert.equal(fs.readFileSync(path.join(dest,'converter/docling_dev/api.py'),'utf8'),'changed in 2.1.2');
  assert.equal(fs.readFileSync(path.join(dest,'.converter-previous/main.py'),'utf8'),'old main.py');
  ok('Rollback',dest);
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
  assert.equal(fs.readFileSync(path.join(dest,'converter/pyruntime/vcruntime140.dll'),'utf8'),'old Python runtime');
  console.log('ok: skip intermediate versions and restore the original converter');

  ok('Prepare',dest,options);
  fs.renameSync(path.join(dest,'converter'),path.join(dest,'.converter-previous'));
  write(path.join(dest,'.converter-update.json'),JSON.stringify({schema:1,phase:'switching',hadTarget:true}));
  ok('Recover',dest);
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
  assert.equal(fs.existsSync(path.join(dest,'.converter-next')),false);
  console.log('ok: recover interruption between directory renames');

  const bad=path.join(work,'truncated.zip');fs.writeFileSync(bad,Buffer.from('not a ZIP'));
  const result=run('Install',dest,['-Zip',bad]);
  assert.notEqual(result.status,0);
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
  assert.equal(fs.existsSync(path.join(dest,'.converter-update.json')),false);
  console.log('ok: truncated archive leaves the working converter intact');

  const badManifest=JSON.parse(JSON.stringify(pkg.converter.manifestData));
  badManifest.files[0].sha256='0'.repeat(64);
  const manifestPath=path.join(work,'bad-manifest.json');write(manifestPath,JSON.stringify(badManifest));
  assert.notEqual(run('Check',dest,['-Zip',path.join(output,'converter.zip'),'-ManifestFile',manifestPath]).status,0);
  assert.notEqual(run('Prepare',dest,['-Zip',path.join(output,'converter.zip'),'-ManifestFile',manifestPath]).status,0);
  assert.equal(fs.existsSync(path.join(dest,'.converter-next')),false);
  assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
  console.log('ok: hash mismatch is rejected before switching');

  const evilScript=path.join(work,'evil.ps1');
  write(evilScript,"param($Zip)\nAdd-Type -AssemblyName System.IO.Compression\nAdd-Type -AssemblyName System.IO.Compression.FileSystem\n$a=[IO.Compression.ZipFile]::Open($Zip,[IO.Compression.ZipArchiveMode]::Create)\n$e=$a.CreateEntry('converter/../../outside.txt')\n$s=$e.Open();$s.WriteByte(65);$s.Dispose();$a.Dispose()\n");
  const evilZip=path.join(work,'evil.zip');
  const created=spawnSync('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',evilScript,'-Zip',evilZip],{encoding:'utf8',windowsHide:true});
  assert.equal(created.status,0,created.stderr);
  assert.notEqual(run('Install',dest,['-Zip',evilZip]).status,0);
  assert.equal(fs.existsSync(path.join(work,'outside.txt')),false);
  console.log('ok: archive traversal is rejected');

  ok('Install',dest,options);
  const originalFetch=global.fetch;
  try {
    let started=false;
    global.fetch=async url=>{
      if(url.endsWith('/health')) return {ok:true};
      if(url.endsWith('/converter/start')) {started=true;return {ok:false,json:async()=>({ok:false})};}
      return {ok:true,json:async()=>({running:false,healthy:false})};
    };
    ok('Check',dest,['-ReserveKB','1']);
    const rollback=await finishPendingUpdate({converterDir:path.join(dest,'converter'),backendPort:12345,currentVersion:'2.1.2',
      run:async action=>ok(action,dest)});
    assert.ok(started);assert.equal(rollback.rolledBack,true);
    assert.equal(fs.readFileSync(path.join(dest,'converter/main.py'),'utf8'),'old main.py');
    const fresh=path.join(work,'fresh-install');
    ok('Install',fresh,options);
    const firstFailure=await finishPendingUpdate({converterDir:path.join(fresh,'converter'),backendPort:12345,currentVersion:'2.1.2',
      run:async action=>ok(action,fresh)});
    assert.equal(firstFailure.failed,true);
    assert.equal(firstFailure.rolledBack,false);
    assert.equal(fs.existsSync(path.join(fresh,'.converter-update.json')),false);
    ok('Install',dest,options);
    global.fetch=async url=>({ok:true,json:async()=>url.endsWith('/converter/start')?{ok:true,external:false}:{running:true,healthy:true}});
    const confirmed=await finishPendingUpdate({converterDir:path.join(dest,'converter'),backendPort:12345,currentVersion:'2.1.2',
      run:async action=>ok(action,dest)});
    assert.equal(confirmed.confirmed,true);
    assert.equal(fs.existsSync(path.join(dest,'.converter-previous')),false);
  } finally {global.fetch=originalFetch;}
  for(const prefix of ['pyruntime','.venv/Lib/site-packages/torch/lib']) {
    for(const name of ['msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'])fs.copyFileSync(path.join(runtimeDir,name),path.join(dest,'converter',prefix,name));
  }
  assert.equal(await converterMatches(path.join(dest,'converter'),pkg.converter.manifestData),true);
  fs.unlinkSync(path.join(dest,'converter/converter-manifest.json'));
  assert.equal(await converterMatches(path.join(dest,'converter'),pkg.converter.manifestData),true);
  ok('Check',dest,options);
  assert.equal(fs.existsSync(path.join(dest,'converter/converter-manifest.json')),false,'Check must remain readonly');
  ok('Install',dest,options);
  assert.equal(fs.existsSync(path.join(dest,'.converter-update.json')),false,'Unchanged converter must not be replaced');
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(dest,'converter/converter-manifest.json'))),pkg.converter.manifestData);
  write(path.join(dest,'converter/unexpected.dll'),'extra runtime file');
  ok('Prepare',dest,options);
  assert.equal(fs.existsSync(path.join(dest,'.converter-update.json')),true,'Extra runtime file requires replacement');
  ok('Recover',dest);
  fs.unlinkSync(path.join(dest,'converter/unexpected.dll'));

  const changed=fs.readFileSync(path.join(dest,'converter/main.py'));
  changed[0] ^= 1;
  fs.writeFileSync(path.join(dest,'converter/main.py'),changed);
  assert.equal(await converterMatches(path.join(dest,'converter'),pkg.converter.manifestData),false);
  console.log('ok: startup failure rolls back, successful owned startup confirms');

  const before=fs.readFileSync(path.join(output,'update-package.json'),'utf8');
  const incompleteRuntime=path.join(work,'incomplete-runtime');
  write(path.join(incompleteRuntime,'vcruntime140.dll'),'incomplete fixture');
  await assert.rejects(buildUpdate({releaseDir:release,converterDir:src,runtimeDir:incompleteRuntime,version:'2.1.2'}),/Visual C\+\+ runtime is incomplete/);
  assert.equal(fs.readFileSync(path.join(output,'update-package.json'),'utf8'),before);
  feed(release,'2.1.3');
  await assert.rejects(buildUpdate({releaseDir:release,converterDir:path.join(work,'missing'),version:'2.1.3'}));
  assert.equal(fs.readFileSync(path.join(output,'update-package.json'),'utf8'),before);
  const archive=path.join(output,'converter.zip');
  fs.appendFileSync(archive,'corruption');
  await assert.rejects(inspectPackage(output));
  console.log('ok: failed package build preserves previous output; damaged package rejected');
}
main().then(()=>console.log('Universal package and recovery checks passed.')).catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  const full=fs.realpathSync(work);
  assert.equal(path.dirname(full).toLowerCase(),fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(full).startsWith('sberact-update-test-'));
  fs.rmSync(full,{recursive:true,force:true});
});
