const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {inspectPackage,digest}=require('../../electron-app/update-package');

async function main() {
  const directory=path.resolve(process.argv[2] || 'temp/offline-update-build/SberAct-Update');
  const pkg=await inspectPackage(directory);
  assert.ok(pkg.converter,'A full OCR package is required');
  const runtime=path.resolve(process.argv[3] || path.join(directory,'../win-unpacked/resources/msvc-runtime'));
  const expected=pkg.converter.manifestData.files;
  for(const prefix of ['pyruntime','.venv/Lib/site-packages/torch/lib']) {
    for(const name of ['msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll']) {
      const file=expected.find(file=>file.path===prefix+'/'+name);
      assert.ok(file,'Missing bundled runtime: '+prefix+'/'+name);
      assert.equal(file.sha256,await digest(path.join(runtime,name)),'Runtime must match the application build');
    }
  }
  const output=path.join(directory,'..','full-archive-validation');
  assert.ok(!fs.existsSync(path.join(output,'converter')),'Validation root must not contain an installed converter');
  const shell=path.join(process.env.WINDIR,'SysWOW64/WindowsPowerShell/v1.0/powershell.exe');
  assert.ok(fs.existsSync(shell),'32-bit PowerShell is required for this installer check');
  const started=Date.now();
  await new Promise((resolve,reject)=>{
    const child=spawn(shell,['-NoProfile','-ExecutionPolicy','Bypass','-File',path.resolve('scripts/converter-transaction.ps1'),
      '-Action','Check','-Dest',output,'-Zip',path.join(directory,pkg.converter.archive),
      '-ManifestFile',path.join(directory,pkg.converter.manifest)],{stdio:'inherit',windowsHide:true});
    child.on('error',reject);
    child.on('close',code=>code===0?resolve():reject(new Error('Full ZIP validation failed: '+code)));
  });
  const report={
    version:pkg.version,converter:pkg.converter.version,files:expected.length,
    unpackedBytes:pkg.converter.unpackedBytes,archiveBytes:fs.statSync(path.join(directory,pkg.converter.archive)).size,
    runtime:'matches installer build',archiveReader:'32-bit Windows PowerShell',
    allPayloadFiles:'SHA256 verified',seconds:(Date.now()-started)/1000
  };
  fs.writeFileSync(path.join(directory,'..','full-package-verification.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
