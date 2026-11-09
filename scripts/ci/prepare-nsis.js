const fs = require('node:fs');
const path = require('node:path');
async function main() {
  const { NSIS_PATH, NsisTargetOptions } = require('app-builder-lib/out/targets/nsis/nsisUtil');
  NsisTargetOptions.resolve({});
  const directory = await NSIS_PATH();
  const compiler = path.join(directory, 'Bin/makensis.exe');
  if (!fs.existsSync(compiler)) throw new Error('NSIS compiler not found');
  if (process.env.GITHUB_ENV) fs.appendFileSync(process.env.GITHUB_ENV, 'SBERACT_NSIS_DIR=' + directory + '\n');
  console.log('NSIS compiler ready');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
