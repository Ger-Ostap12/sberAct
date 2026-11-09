const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { digest, inspectPackage } = require('../electron-app/update-package');

const excluded = new Set(['.git', '.gitignore', '.gitattributes', '.gitmodules', '__pycache__', 'node_modules', 'tests', 'pdf_to_convert']);
async function converterManifest(directory, version, runtimeDir = null) {
  const files = [];
  async function visit(relative) {
    for (const item of fs.readdirSync(path.join(directory, relative), { withFileTypes: true }).sort((a,b) => a.name.localeCompare(b.name, 'en'))) {
      if (excluded.has(item.name) || /\.(pyc|log)$/i.test(item.name) || item.name === 'converter-manifest.json') continue;
      const name = relative ? relative + '/' + item.name : item.name;
      if (name.startsWith('models/') && /\.part\d*$/i.test(name)) continue;
      const full = path.join(directory, name);
      if (item.isSymbolicLink()) throw new Error('Converter contains a link: ' + name);
      if (item.isDirectory()) await visit(name);
      else if (item.isFile()) files.push({ path: name, size: fs.statSync(full).size, sha256: await digest(full) });
    }
  }
  await visit('');
  for (const name of ['main.py', 'run_converter.py', 'docling_dev/api.py', 'pyruntime/python.exe', 'vendor/tesseract/tesseract.exe']) {
    if (!files.some(f => f.path === name)) throw new Error('Converter is incomplete: ' + name);
  }
  for (const prefix of ['.venv/Lib/site-packages/', 'models/docling/']) {
    if (!files.some(f => f.path.startsWith(prefix))) throw new Error('Converter is incomplete: ' + prefix);
  }
  if (runtimeDir) {
    const libraries = fs.readdirSync(runtimeDir,{withFileTypes:true}).filter(file=>file.isFile() && /\.dll$/i.test(file.name));
    for (const name of ['msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll']) {
      if (!libraries.some(file=>file.name.toLowerCase()===name)) throw new Error('Visual C++ runtime is incomplete: '+name);
    }
    const mapped = new Map(files.map(file=>[file.path.toLowerCase(),file]));
    const prefixes=['pyruntime'];
    if (fs.existsSync(path.join(directory,'.venv/Lib/site-packages/torch/lib'))) prefixes.push('.venv/Lib/site-packages/torch/lib');
    for (const library of libraries) {
      const full=path.join(runtimeDir,library.name);
      const record={size:fs.statSync(full).size,sha256:await digest(full)};
      for (const prefix of prefixes) {
        const relative=prefix+'/'+library.name;
        mapped.set(relative.toLowerCase(),{path:relative,...record});
      }
    }
    files.splice(0,files.length,...mapped.values());
  }
  for (const name of ['msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll']) {
    if (!files.some(file=>file.path.toLowerCase()==='pyruntime/'+name)) throw new Error('Converter runtime is incomplete: '+name);
  }
  files.sort((a,b)=>a.path.localeCompare(b.path,'en'));
  const contentId = crypto.createHash('sha256').update(JSON.stringify(files)).digest('hex');
  return { format: 2, version: contentId.slice(0, 16), appVersion: version, files };
}
function removeBuildDirectory(directory, parent) {
  const resolved = path.resolve(directory);
  if (path.dirname(resolved) !== path.resolve(parent) || !/^SberAct-Update\.(new|old)-/.test(path.basename(resolved)) ||
      fs.lstatSync(resolved).isSymbolicLink()) throw new Error('Unsafe build cleanup path');
  fs.rmSync(resolved, { recursive: true, force: true });
}
async function buildUpdate({ releaseDir, converterDir, version, appOnly = false, runtimeDir }) {
  const release = path.resolve(releaseDir);
  const output = path.join(release, 'SberAct-Update');
  const staging = path.join(release, 'SberAct-Update.new-' + crypto.randomUUID());
  const previous = path.join(release, 'SberAct-Update.old-' + crypto.randomUUID());
  fs.mkdirSync(staging);
  try {
    // Validate the installer and feed before touching the previous distributable.
    const source = await inspectPackage(release, { appArtifactsOnly:true });
    if (source.version !== version) throw new Error('Build version does not match latest.yml.');
    for (const name of ['latest.yml', source.installer, source.installer + '.blockmap']) {
      const from = path.join(release, name);
      if (fs.existsSync(from)) fs.copyFileSync(from, path.join(staging, name));
    }
    let converter = null;
    if (!appOnly) {
      const directory = path.resolve(converterDir);
      if (directory === release || directory.startsWith(staging + path.sep)) throw new Error('Invalid converter staging path');
      console.log('Hashing the complete converter...');
      const runtime=path.resolve(runtimeDir || path.join(release,'win-unpacked/resources/msvc-runtime'));
      const manifest = await converterManifest(directory, version, runtime);
      const manifestFile = path.join(staging, 'converter-manifest.json');
      fs.writeFileSync(manifestFile, JSON.stringify(manifest, null, 2));
      const result = spawnSync('powershell.exe', ['-NoProfile','-ExecutionPolicy','Bypass','-File',
        path.join(__dirname, 'pack-converter.ps1'), '-SourceDir', directory, '-Zip', path.join(staging,'converter.zip'), '-ManifestFile', manifestFile, '-RuntimeDir', runtime],
        { stdio:'inherit', windowsHide:true });
      if (result.error || result.status !== 0) throw result.error || new Error('Converter archive creation failed.');
      converter = { archive:'converter.zip', manifest:'converter-manifest.json', version:manifest.version,
        unpackedBytes:manifest.files.reduce((sum,file)=>sum+file.size,0) };
    }
    const files = [];
    for (const name of fs.readdirSync(staging).sort()) files.push({ path:name, size:fs.statSync(path.join(staging,name)).size, sha256:await digest(path.join(staging,name)) });
    fs.writeFileSync(path.join(staging,'update-package.json'), JSON.stringify({ schema:1, version, converter, files },null,2));
    await inspectPackage(staging);
    if (fs.existsSync(output)) {
      if (fs.lstatSync(output).isSymbolicLink()) throw new Error('Update output is a link');
      fs.renameSync(output,previous);
    }
    try { fs.renameSync(staging,output); } catch(error) {
      if (fs.existsSync(previous)) fs.renameSync(previous,output);
      throw error;
    }
    if (fs.existsSync(previous)) removeBuildDirectory(previous,release);
    console.log('Complete update package: ' + output);
    return output;
  } catch(error) {
    if (fs.existsSync(staging)) removeBuildDirectory(staging,release);
    throw error;
  }
}
module.exports = { buildUpdate, converterManifest };
if (require.main === module) {
  const args = process.argv.slice(2);
  const root = path.resolve(__dirname,'..');
  const options = { releaseDir:path.join(root,'release'),converterDir:path.join(root,'release/converter'),version:require('../package.json').version };
  for (let i=0;i<args.length;i++) {
    const key=args[i].toLowerCase();
    if (key==='-apponly') options.appOnly=true;
    else if (key==='-includeconverter') { /* Full converter is now the default. */ }
    else if (key==='-converterdir') options.converterDir=args[++i];
    else throw new Error('Unknown option: '+args[i]+'. Full packages no longer use a delta baseline.');
  }
  buildUpdate(options).catch(error=>{console.error(error.message);process.exitCode=1;});
}
