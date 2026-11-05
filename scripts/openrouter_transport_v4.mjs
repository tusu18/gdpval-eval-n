// Explicit HTTP/1.1 upload with backpressure and verified TLS. No redirects.
import https from 'node:https';
import { readFileSync } from 'node:fs';
import { once } from 'node:events';
const {key,route,body}=JSON.parse(readFileSync(0,'utf8'));
if(!/^[A-Za-z0-9_-]{32,256}$/.test(key)||!['key','chat/completions'].includes(route))throw Error('Invalid transport input');
const bytes=body===undefined?null:Buffer.from(JSON.stringify(body));
try{
 const result=await new Promise((resolve,reject)=>{
  let sent=false,responseStarted=false,sendTimer;
  const headers={Authorization:`Bearer ${key}`,'Content-Type':'application/json','X-Title':'Turing matched workflow development'};
  if(bytes){headers['Content-Length']=String(bytes.length);headers.Expect='100-continue';}
  const req=https.request({hostname:'openrouter.ai',port:443,path:`/api/v1/${route}`,method:bytes?'POST':'GET',headers,agent:false},res=>{
   responseStarted=true;clearTimeout(sendTimer);let chunks=[];let size=0;
   res.on('data',c=>{size+=c.length;if(size>20000000)req.destroy(Error('Response size limit'));else chunks.push(c)});
   res.on('error',reject);res.on('end',()=>resolve({status:res.statusCode,raw:Buffer.concat(chunks).toString('utf8')}));
  });
  req.setTimeout(900000,()=>req.destroy(Error('Request timed out')));req.on('error',reject);
  async function send(){
   if(sent||responseStarted)return;sent=true;clearTimeout(sendTimer);
   try{for(let i=0;i<bytes.length;i+=32768){if(req.destroyed)throw Error('Upload connection closed');if(!req.write(bytes.subarray(i,i+32768)))await once(req,'drain');}req.end();}
   catch(e){req.destroy();reject(e);}
  }
  if(bytes){req.on('continue',send);req.flushHeaders();sendTimer=setTimeout(send,1500);}else req.end();
 });
 if(result.status<200||result.status>=300)throw Error(`OpenRouter HTTP ${result.status}: ${result.raw.slice(0,1500)}`);
 const data=JSON.parse(result.raw);if(data.error)throw Error(`OpenRouter response error: ${JSON.stringify(data.error).slice(0,1000)}`);
 process.stdout.write(JSON.stringify(data));
}catch(e){process.stderr.write([e.code,e.message].filter(Boolean).join('; ').replaceAll(key,'[REDACTED]').replace(/"user_id"\s*:\s*"[^"]+"/g,'"user_id":"[REDACTED]"').slice(0,1800));process.exitCode=1;}
