// One physical request, no retries or redirects. Credential arrives only on stdin.
import https from 'node:https';
import {readFileSync} from 'node:fs';
import {once} from 'node:events';
const {key,route,body,timeout_ms=240000}=JSON.parse(readFileSync(0,'utf8'));
if(!/^[A-Za-z0-9_-]{32,256}$/.test(key)||!['key','chat/completions','responses'].includes(route))throw Error('Invalid transport request');
const bytes=body===undefined?null:Buffer.from(JSON.stringify(body));
let sent=false;
try {
 const response=await new Promise((resolve,reject)=>{
  const headers={Authorization:`Bearer ${key}`,'Content-Type':'application/json','X-Title':'Turing original GDPval evaluation v2','X-OpenRouter-Metadata':'enabled'};
  if(bytes){headers['Content-Length']=String(bytes.length);headers.Expect='100-continue';}
  let sendTimer,responseStarted=false;
  const req=https.request({hostname:'openrouter.ai',path:`/api/v1/${route}`,method:bytes?'POST':'GET',headers,agent:false},res=>{
   responseStarted=true;clearTimeout(sendTimer);let size=0,parts=[];
   res.on('data',chunk=>{size+=chunk.length;if(size>25000000)req.destroy(Error('response_size_limit'));else parts.push(chunk)});
   res.on('error',reject);
   res.on('end',()=>resolve({status:res.statusCode,headers:{'retry-after':res.headers['retry-after']??null},body:Buffer.concat(parts).toString('utf8'),request_body_sent:sent}));
  });
  req.setTimeout(timeout_ms,()=>req.destroy(Error('transport_timeout')));
  req.on('error',error=>{clearTimeout(sendTimer);reject(error)});
  async function send(){
   if(sent||responseStarted)return;sent=true;clearTimeout(sendTimer);
   try{for(let i=0;i<bytes.length;i+=32768){if(req.destroyed)throw Error('upload_closed');if(!req.write(bytes.subarray(i,i+32768)))await once(req,'drain');}req.end()}
   catch(error){req.destroy();reject(error)}
  }
  if(bytes){req.on('continue',send);req.flushHeaders();sendTimer=setTimeout(send,1500)}else req.end();
 });
 try{response.body=JSON.parse(response.body)}catch{response.body={unparsed_response:response.body.slice(0,1000)}}
 process.stdout.write(JSON.stringify(response).replaceAll(key,'[REDACTED]').replace(/"user_id"\s*:\s*"[^"]+"/g,'"user_id":"[REDACTED]"'));
}catch(e){
 process.stdout.write(JSON.stringify({status:null,request_body_sent:sent,transport_error:String(e.message).replaceAll(key,'[REDACTED]').slice(0,300)}));
}
