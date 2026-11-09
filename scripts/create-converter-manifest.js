const fs=require('node:fs');
const path=require('node:path');
const {converterManifest}=require('./build-update');
converterManifest(process.argv[2],require('../package.json').version,process.argv[3] || null).then(manifest=>fs.writeFileSync(path.join(process.argv[2],'converter-manifest.json'),JSON.stringify(manifest,null,2))).catch(error=>{console.error(error);process.exitCode=1;});
