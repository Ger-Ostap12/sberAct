const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

function transaction(action, converterDir, options = {}) {
  const script = options.script || (process.resourcesPath
    ? path.join(process.resourcesPath, 'update-tools/converter-transaction.ps1')
    : path.join(__dirname, '../scripts/converter-transaction.ps1'));
  const args = ['-NoProfile','-ExecutionPolicy','Bypass','-File',script,'-Action',action,'-Dest',path.dirname(converterDir)];
  if (options.zip) args.push('-Zip',options.zip);
  if (options.manifest) args.push('-ManifestFile',options.manifest);
  return new Promise((resolve,reject)=>{
    const child = spawn('powershell.exe',args,{ windowsHide:true, stdio:['ignore','pipe','pipe'] });
    let stdout='', stderr='';
    child.stdout.on('data',chunk=>{ stdout=(stdout+chunk.toString('utf8')).slice(-16000); });
    child.stderr.on('data',chunk=>{ stderr=(stderr+chunk.toString('utf8')).slice(-16000); });
    child.on('error',reject);
    child.on('close',code=>{
      if (code!==0) reject(new Error("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043c\u043e\u0434\u0443\u043b\u044c \u043a\u043e\u043d\u0432\u0435\u0440\u0442\u0430\u0446\u0438\u0438. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438:\n"+stderr));
      else resolve(stdout);
    });
  });
}
async function state(converterDir) {
  const file=path.join(path.dirname(converterDir),'.converter-update.json');
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function stopConverter(backendPort) {
  const base='http://127.0.0.1:'+backendPort;
  const stopped=await fetch(base+'/converter/stop',{method:'POST',signal:AbortSignal.timeout(10000)});
  if (!stopped.ok) throw new Error('Не удалось остановить конвертер. Обновление не применено.');
  for (let i=0;i<40;i++) {
    const response=await fetch(base+'/converter/status',{signal:AbortSignal.timeout(3000)});
    if (!response.ok) throw new Error('Не удалось проверить остановку конвертера.');
    const status=await response.json();
    if (!status.running && !status.healthy) return;
    await delay(250);
  }
  throw new Error('Конвертер ещё работает. Закройте другие экземпляры и повторите обновление.');
}
async function finishPendingUpdate({converterDir,backendPort,currentVersion,run=transaction}) {
  const current=await state(converterDir);
  if (!current || current.phase!=='pending') return { pending:false };
  const base='http://127.0.0.1:'+backendPort;
  for (let i=0;i<60;i++) {
    try {
      const response=await fetch(base+'/health',{signal:AbortSignal.timeout(2000)});
      if (response.ok) break;
    } catch (_) { /* Backend is still starting. */ }
    if (i===59) throw new Error('Проверка конвертера отложена: backend не запустился. Резервная копия сохранена.');
    await delay(1000);
  }
  try {
    const manifestFile=path.join(converterDir,'converter-manifest.json');
    const manifest=fs.existsSync(manifestFile)?JSON.parse(fs.readFileSync(manifestFile,'utf8').replace(/^\uFEFF/,'')):null;
    if (manifest && manifest.appVersion && require('semver').gt(manifest.appVersion,currentVersion)) {
      throw new Error('Установка новой версии приложения не завершилась.');
    }
    const response=await fetch(base+'/converter/start',{method:'POST',signal:AbortSignal.timeout(190000)});
    const result=await response.json();
    if (!response.ok || !result.ok || result.external) throw new Error('Новый конвертер не прошёл проверку запуска.');
    const statusResponse=await fetch(base+'/converter/status',{signal:AbortSignal.timeout(5000)});
    const status=await statusResponse.json();
    if (!statusResponse.ok || !status.running || !status.healthy) throw new Error('Новый конвертер не отвечает.');
  } catch(error) {
    await stopConverter(backendPort);
    await run('Rollback',converterDir);
    return { rolledBack:current.hadTarget, failed:!current.hadTarget, message:error.message };
  }
  await run('Confirm',converterDir);
  return { confirmed:true };
}
module.exports={ transaction,state,stopConverter,finishPendingUpdate };
