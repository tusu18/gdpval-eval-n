// Credentials and request bodies arrive through stdin and are never persisted.
import { readFileSync } from 'node:fs';
const { key, route, body } = JSON.parse(readFileSync(0, 'utf8'));
if (!/^[A-Za-z0-9_-]{32,256}$/.test(key) || !['key','models','chat/completions'].includes(route)) throw new Error('Invalid transport input');
try {
  const response = await fetch(`https://openrouter.ai/api/v1/${route}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {Authorization:`Bearer ${key}`, 'Content-Type':'application/json', 'X-Title':'Turing paired development study'},
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(900000),
    redirect: 'error',
  });
  const raw = await response.text();
  if (!response.ok) {
    const safe = raw.replaceAll(key,'[REDACTED]').replace(/"user_id"\s*:\s*"[^"]+"/g,'"user_id":"[REDACTED]"');
    throw new Error(`OpenRouter HTTP ${response.status}: ${safe.slice(0,1500)}`);
  }
  const data = JSON.parse(raw);
  if (data.error) throw new Error(`OpenRouter response error: ${JSON.stringify(data.error).slice(0,1000)}`);
  process.stdout.write(JSON.stringify(data));
} catch (e) {
  const msg = [e.message,e.cause?.code,e.cause?.message].filter(Boolean).join('; ').replaceAll(key,'[REDACTED]');
  process.stderr.write(msg.slice(0,1800)); process.exitCode=1;
}
