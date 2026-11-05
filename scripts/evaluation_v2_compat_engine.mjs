// Versioned error-reporting wrapper; the original native engine is unchanged.
import fs from 'node:fs/promises';
let recorded=false;
async function report(error){
  if(recorded)return;recorded=true;
  const result={name:error?.name||'Error',message:String(error?.message||error),stack:String(error?.stack||'').slice(0,6000)};
  try{const job=JSON.parse(await fs.readFile(process.argv[2],'utf8'));await fs.writeFile(job.result+'.error.json',JSON.stringify(result,null,2)+'\n');}catch{}
  process.stderr.write(JSON.stringify(result)+'\n');process.exitCode=1;
}
process.on('uncaughtException',report);process.on('unhandledRejection',report);
try{await import('./evaluation_v2_engine.mjs');}catch(error){await report(error);}
