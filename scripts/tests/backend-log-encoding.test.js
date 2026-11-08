const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { PassThrough } = require('node:stream');
const { captureUtf8Output, createServiceLog } = require('../../electron-app/serviceLog');
const { createDiagnostics } = require('../../electron-app/diagnostics');

test('split UTF-8 stdout and stderr survive in both service log and developer report', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sber-log-encoding-'));
  try {
    const log = createServiceLog('backend', dir);
    const journal = createDiagnostics(dir);
    const stdout = new PassThrough();
    const stderr = new PassThrough();
    captureUtf8Output(stdout, text => { log.write(text); journal.ingest('backend', text, 'stdout'); });
    captureUtf8Output(stderr, text => { log.write(text); journal.ingest('backend', text, 'stderr'); });
    const message = 'INFO:formatting_mixin:\u041f\u0440\u0438\u043c\u0435\u043d\u0451\u043d \u0441\u0442\u0438\u043b\u044c: Intense Quote\n';
    const error = 'ERROR:backend:\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0438\u0441\u0438\n';
    const done = Promise.all([stdout, stderr].map(stream => new Promise(resolve => stream.on('end', resolve))));
    const outBytes = Buffer.from(message), errBytes = Buffer.from(error);
    for (let i = 0; i < Math.max(outBytes.length, errBytes.length); i++) {
      if (i < outBytes.length) stdout.write(outBytes.subarray(i, i + 1));
      if (i < errBytes.length) stderr.write(errBytes.subarray(i, i + 1));
    }
    stdout.end(); stderr.end();
    await done;
    const report = journal.snapshot().events.map(event => event.message);
    assert(report.includes(message.trim()));
    assert(report.includes(error.trim()));
    journal.ingest('backend', 'stdout tail', 'stdout');
    journal.ingest('backend', 'stderr tail', 'stderr');
    journal.flush('backend', 'stdout');
    journal.flush('backend', 'stderr');
    const flushed = journal.snapshot().events.map(event => event.message);
    assert(flushed.includes('stdout tail'));
    assert(flushed.includes('stderr tail'));
    assert(!flushed.includes('stdout tailstderr tail'));
    const raw = fs.readFileSync(log.file, 'utf8');
    assert(!raw.includes('\ufffd'));
  } finally {
    assert.equal(path.dirname(path.resolve(dir)), path.resolve(os.tmpdir()));
    assert(path.basename(dir).startsWith('sber-log-encoding-'));
    fs.rmSync(dir, {recursive:true, force:true});
  }
});

test('backend startup changes legacy pipes to UTF-8 before logging and configures child Python', async () => {
  const hook = path.resolve('python-backend/app/stdio_encoding.py');
  const python = path.resolve('python-backend/venv/Scripts/python.exe');
  const message = '\u041f\u0440\u0438\u043c\u0435\u043d\u0451\u043d \u0441\u0442\u0438\u043b\u044c \u0434\u043b\u044f \u0430\u0431\u0437\u0430\u0446\u0430: Intense Quote';
  const code = [
    'import sys, runpy, logging, os, subprocess',
    "sys.stdout.reconfigure(encoding='cp1251')",
    "sys.stderr.reconfigure(encoding='cp1251')",
    'sys.frozen = True',
    'runpy.run_path(sys.argv[1])',
    'message = sys.argv[2]',
    'print(message)',
    "logging.warning(message)",
    "assert os.environ['PYTHONIOENCODING'] == 'utf-8:backslashreplace'",
    "assert os.environ['PYTHONUTF8'] == '1'",
    "subprocess.run([sys.executable, '-c', 'import sys; print(sys.argv[1])', message], check=True)",
  ].join('\n');
  const child = spawn(python, ['-c', code, hook, message], { windowsHide:true });
  let stdout = '', stderr = '';
  captureUtf8Output(child.stdout, text => { stdout += text; });
  captureUtf8Output(child.stderr, text => { stderr += text; });
  const result = await new Promise((resolve, reject) => {
    child.on('error', reject);child.on('close', resolve);
  });
  assert.equal(result, 0, stderr);
  assert.equal(stdout.replace(/\r/g,''), message + '\n' + message + '\n');
  assert.equal(stderr.replace(/\r/g,''), 'WARNING:root:' + message + '\n');
  assert(!stdout.includes('\ufffd') && !stderr.includes('\ufffd'));
});
