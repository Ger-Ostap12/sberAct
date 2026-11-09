const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const yaml = require('js-yaml');
const semver = require('semver');

function relativeFile(value) {
  if (typeof value !== 'string' || !value || /[\\:<>\"|?*\x00-\x1f]/.test(value) ||
      value.split('/').some(p => !p || p === '.' || p === '..' || /[. ]$/.test(p) || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)/i.test(p))) {
    throw new Error('Недопустимый путь в комплекте обновления.');
  }
  return value;
}
function safeFile(root, relative) {
  relativeFile(relative);
  let cursor = path.resolve(root);
  for (const part of relative.split('/')) {
    cursor = path.join(cursor, part);
    if (fs.existsSync(cursor) && fs.lstatSync(cursor).isSymbolicLink()) throw new Error('Комплект содержит ссылку вместо файла.');
  }
  return cursor;
}
function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
}
async function digest(file, algorithm = 'sha256', encoding = 'hex') {
  const hash = crypto.createHash(algorithm);
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest(encoding);
}
function validateManifest(manifest) {
  if (!manifest || !Array.isArray(manifest.files) || !manifest.files.length) throw new Error('Пустой манифест конвертера.');
  const seen = new Set();
  for (const file of manifest.files) {
    relativeFile(file.path);
    const key = file.path.toLowerCase();
    if (key === 'converter-manifest.json' || seen.has(key) || !/^[a-f0-9]{64}$/i.test(file.sha256) ||
        !Number.isSafeInteger(file.size) || file.size < 0) throw new Error('Некорректный манифест конвертера.');
    seen.add(key);
  }
  return manifest;
}
async function verifyFile(root, entry) {
  if (!entry || !Number.isSafeInteger(entry.size) || entry.size < 0 || !/^[a-f0-9]{64}$/i.test(entry.sha256)) throw new Error('Некорректная контрольная сумма комплекта.');
  const file = safeFile(root, entry.path);
  const stat = fs.statSync(file);
  if (!stat.isFile() || stat.size !== entry.size || await digest(file) !== entry.sha256.toLowerCase()) {
    throw new Error('Комплект повреждён или скопирован не полностью: ' + entry.path);
  }
}
async function inspectPackage(root, { appArtifactsOnly = false } = {}) {
  const feedText = fs.readFileSync(path.join(root, 'latest.yml'), 'utf8');
  const feed = yaml.load(feedText);
  const feedId = crypto.createHash('sha256').update(feedText).digest('hex');
  if (!feed || !semver.valid(feed.version) || !Array.isArray(feed.files) || !feed.files.length) throw new Error('Некорректный latest.yml.');
  const installer = feed.files[0];
  if (!installer.url || !installer.url.toLowerCase().endsWith('.exe') || typeof installer.sha512 !== 'string' ||
      !Number.isSafeInteger(installer.size) || installer.size <= 0) throw new Error('В latest.yml отсутствует установщик.');
  const installerPath = safeFile(root, installer.url);
  if (fs.statSync(installerPath).size !== installer.size || await digest(installerPath, 'sha512', 'base64') !== installer.sha512) {
    throw new Error('Установщик повреждён или не соответствует latest.yml.');
  }
  if (appArtifactsOnly) return { root, version:feed.version, installer:installer.url };
  const metadataPath = path.join(root, 'update-package.json');
  if (!fs.existsSync(metadataPath)) {
    if (fs.existsSync(path.join(root, 'converter-manifest.json')) || fs.existsSync(path.join(root, 'converter.zip'))) {
      throw new Error('Это прежний формат обновления конвертера. Подготовьте полный комплект новой командой build:update.');
    }
    return { root, version: feed.version, installer: installer.url, converter: null, identity:installer.sha512 + feedId };
  }
  const metadataText = fs.readFileSync(metadataPath,'utf8');
  const metadata = JSON.parse(metadataText.replace(/^\uFEFF/,''));
  if (metadata.schema !== 1 || metadata.version !== feed.version || !Array.isArray(metadata.files)) throw new Error('Версия комплекта не соответствует latest.yml.');
  const seen = new Set();
  for (const file of metadata.files) {
    const key = relativeFile(file.path).toLowerCase();
    if (seen.has(key)) throw new Error('Повтор файла в комплекте.');
    seen.add(key);
    await verifyFile(root, file);
  }
  for (const name of ['latest.yml', installer.url]) if (!seen.has(name.toLowerCase())) throw new Error('Неполный манифест комплекта.');
  let converter = null;
  if (metadata.converter) {
    if (metadata.converter.archive !== 'converter.zip' || metadata.converter.manifest !== 'converter-manifest.json' ||
        !seen.has('converter.zip') || !seen.has('converter-manifest.json')) throw new Error('Неполный комплект конвертера.');
    const manifest = validateManifest(readJson(safeFile(root, metadata.converter.manifest)));
    if (metadata.converter.version !== manifest.version || !Number.isSafeInteger(metadata.converter.unpackedBytes) ||
        metadata.converter.unpackedBytes !== manifest.files.reduce((sum,file)=>sum+file.size,0)) throw new Error('Invalid converter package size or version.');
    converter = { ...metadata.converter, manifestData: manifest };
  }
  return { root, version: feed.version, installer: installer.url, converter, identity:installer.sha512 + ':' + feedId + ':' + crypto.createHash('sha256').update(metadataText).digest('hex') };
}
function ignoredConverterPath(relative) {
  const parts=relative.split('/');
  if(parts.some(part=>['.git','.gitignore','.gitattributes','.gitmodules','__pycache__','node_modules','tests','pdf_to_convert','converter-manifest.json'].includes(part.toLowerCase())))return true;
  if(/\.(pyc|log)$/i.test(relative))return true;
  if(relative.toLowerCase().startsWith('models/') && /\.part\d*$/i.test(relative))return true;
  return /^\.converter-manifest-[0-9a-f-]{36}\.tmp$/i.test(relative) || /(^|\/)\.sbc-[0-9a-f]{16}$/i.test(relative);
}
function checkedConverterRoot(directory) {
  const root=path.resolve(directory);
  let cursor=root;
  while(true) {
    try { if(fs.lstatSync(cursor).isSymbolicLink())throw new Error('Папка конвертера содержит ссылку: '+cursor); }
    catch(error){if(error.code!=='ENOENT')throw error;}
    const parent=path.dirname(cursor);
    if(parent===cursor)break;
    cursor=parent;
  }
  return root;
}
async function compareConverter(directory, manifest) {
  validateManifest(manifest);
  const root=checkedConverterRoot(directory);
  const directories=new Map();
  const expected=new Set(manifest.files.map(file=>file.path.toLowerCase()));
  const result={
    matches:false,totalFiles:manifest.files.length,totalBytes:manifest.files.reduce((sum,file)=>sum+file.size,0),
    unchangedFiles:0,unchangedBytes:0,changedFiles:0,changedBytes:0,missingFiles:0,missingBytes:0,
    extraFiles:0,extraBytes:0
  };
  function installedPath(relative) {
    const parts=relative.split('/');
    let cursor=root;
    for(const part of parts.slice(0,-1)) {
      cursor=path.join(cursor,part);
      if(!directories.has(cursor)) {
        try {
          const info=fs.lstatSync(cursor);
          if(info.isSymbolicLink())throw new Error('Папка конвертера содержит ссылку: '+cursor);
          directories.set(cursor,info.isDirectory());
        } catch(error){if(!['ENOENT','ENOTDIR'].includes(error.code))throw error;directories.set(cursor,false);}
      }
      if(!directories.get(cursor))return null;
    }
    return path.join(root,...parts);
  }
  for(const file of manifest.files) {
    const installed=installedPath(file.path);
    let info;
    try {if(installed)info=fs.lstatSync(installed);}
    catch(error){if(!['ENOENT','ENOTDIR'].includes(error.code))throw error;}
    if(!info){result.missingFiles++;result.missingBytes+=file.size;continue;}
    if(info.isSymbolicLink())throw new Error('Файл конвертера содержит ссылку: '+file.path);
    let same=false;
    if(info.isFile() && info.size===file.size) {
      try {
        const hash=await digest(installed);
        const after=fs.lstatSync(installed);
        if(after.isSymbolicLink())throw new Error('Файл конвертера изменён во время проверки: '+file.path);
        same=hash===file.sha256.toLowerCase() && after.size===info.size && after.mtimeMs===info.mtimeMs && after.ctimeMs===info.ctimeMs;
      } catch(error){if(!['ENOENT','ENOTDIR'].includes(error.code))throw error;}
    }
    if(same){result.unchangedFiles++;result.unchangedBytes+=file.size;}
    else {result.changedFiles++;result.changedBytes+=file.size;}
  }
  const pending=[''];
  while(pending.length) {
    const relative=pending.pop();
    let entries;
    try {entries=fs.readdirSync(path.join(root,relative),{withFileTypes:true});}
    catch(error){if(error.code==='ENOENT')continue;throw error;}
    for(const entry of entries) {
      const name=relative?relative+'/'+entry.name:entry.name;
      if(entry.isSymbolicLink())throw new Error('Папка конвертера содержит ссылку: '+name);
      if(ignoredConverterPath(name))continue;
      if(entry.isDirectory())pending.push(name);
      else if(!expected.has(name.toLowerCase())){
        result.extraFiles++;
        result.extraBytes+=fs.statSync(path.join(root,name)).size;
      }
    }
  }
  result.matches=result.changedFiles===0 && result.missingFiles===0 && result.extraFiles===0;
  return result;
}
function recordConverterManifest(directory,manifest,comparison) {
  if(!comparison.matches)throw new Error('Нельзя записать манифест непроверенного конвертера.');
  const root=checkedConverterRoot(directory);
  const file=safeFile(root,'converter-manifest.json');
  try {
    const current=readJson(file);
    if(JSON.stringify(current)===JSON.stringify(manifest))return;
  } catch(error){if(error.code!=='ENOENT' && !(error instanceof SyntaxError))throw error;}
  const temporary=path.join(root,'.converter-manifest-'+crypto.randomUUID()+'.tmp');
  let owned=false;
  try {
    const descriptor=fs.openSync(temporary,'wx');
    owned=true;
    try {fs.writeFileSync(descriptor,JSON.stringify(manifest,null,2),'utf8');fs.fsyncSync(descriptor);}
    finally {fs.closeSync(descriptor);}
    fs.renameSync(temporary,file);
  } finally {if(owned && fs.existsSync(temporary))fs.unlinkSync(temporary);}
}
async function converterMatches(directory,manifest) {
  return (await compareConverter(directory,manifest)).matches;
}
module.exports = { inspectPackage, converterMatches, compareConverter, recordConverterManifest, validateManifest, safeFile, relativeFile, digest, readJson };
