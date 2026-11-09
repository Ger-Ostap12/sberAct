const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const crypto=require('node:crypto');
const {compareConverter,recordConverterManifest}=require('../../electron-app/update-package');
const work=fs.mkdtempSync(path.join(os.tmpdir(),'sberact-compare-'));
const manifest={version:'test',files:[
  {path:'main.py',size:4,sha256:crypto.createHash('sha256').update('code').digest('hex')},
  {path:'nested/data',size:3,sha256:crypto.createHash('sha256').update('abc').digest('hex')}
]};
async function main(){
  let result=await compareConverter(path.join(work,'missing'),manifest);
  assert.equal(result.missingFiles,2);assert.equal(result.missingBytes,7);
  fs.mkdirSync(path.join(work,'nested'));
  fs.writeFileSync(path.join(work,'main.py'),'code');
  fs.writeFileSync(path.join(work,'nested/data'),'abc');
  fs.mkdirSync(path.join(work,'__pycache__'));
  fs.writeFileSync(path.join(work,'__pycache__/junk.pyc'),'cache');
  fs.writeFileSync(path.join(work,'.gitignore'),'ignored');
  fs.writeFileSync(path.join(work,'runtime.log'),'log');
  result=await compareConverter(work,manifest);
  assert.equal(result.matches,true,'Legacy installation without metadata must match real bytes');
  recordConverterManifest(work,manifest,result);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(work,'converter-manifest.json'))),manifest);
  fs.writeFileSync(path.join(work,'converter-manifest.json'),'{invalid legacy metadata');
  result=await compareConverter(work,manifest);
  assert.equal(result.matches,true);
  recordConverterManifest(work,manifest,result);
  fs.writeFileSync(path.join(work,'main.py'),'Code');
  result=await compareConverter(work,manifest);
  assert.equal(result.matches,false);assert.equal(result.changedFiles,1);assert.equal(result.changedBytes,4);
  assert.throws(()=>recordConverterManifest(work,manifest,result));
  fs.writeFileSync(path.join(work,'main.py'),'code');
  fs.unlinkSync(path.join(work,'nested/data'));
  fs.writeFileSync(path.join(work,'extra.dll'),'extra');
  result=await compareConverter(work,manifest);
  assert.equal(result.missingFiles,1);assert.equal(result.extraFiles,1);assert.equal(result.extraBytes,5);
  fs.unlinkSync(path.join(work,'extra.dll'));
  fs.writeFileSync(path.join(work,'nested/data'),'abc');
  fs.renameSync(path.join(work,'nested'),path.join(work,'real'));
  fs.symlinkSync(path.join(work,'real'),path.join(work,'nested'),'junction');
  await assert.rejects(compareConverter(work,manifest));
  fs.unlinkSync(path.join(work,'nested'));
  fs.renameSync(path.join(work,'real'),path.join(work,'nested'));
  fs.writeFileSync(path.join(work,'converter-manifest.json'),'{}');
  fs.chmodSync(path.join(work,'converter-manifest.json'),0o444);
  result=await compareConverter(work,manifest);
  assert.equal(result.matches,true);
  assert.throws(()=>recordConverterManifest(work,manifest,result));
  assert.equal((await compareConverter(work,manifest)).matches,true);
  fs.chmodSync(path.join(work,'converter-manifest.json'),0o666);
  console.log('Converter comparison passed: missing metadata, stale metadata, exact differences, cache exclusions, links, readonly metadata.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{
  const resolved=fs.realpathSync(work);
  assert.equal(path.dirname(resolved).toLowerCase(),fs.realpathSync(os.tmpdir()).toLowerCase());
  assert.ok(path.basename(resolved).startsWith('sberact-compare-'));
  fs.rmSync(resolved,{recursive:true,force:true});
});
