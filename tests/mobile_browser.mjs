// Native Node WebSocket + Chromium CDP; no browser automation dependency.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const [debug, url, width, height, shot] = process.argv.slice(2);
const targets = await (await fetch(debug + '/json/list')).json();
const target = targets.find(t => t.type === 'page');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject) => {socket.onopen=resolve;socket.onerror=reject;});
let id = 0;
const waiting = new Map(), errors = [], requests = [];
socket.onmessage = e => {
  const m=JSON.parse(e.data);
  if (m.id) {const p=waiting.get(m.id);waiting.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}
  if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
  if(m.method==='Network.requestWillBeSent' && m.params.request.method==='POST') requests.push(new URL(m.params.request.url).pathname);
};
function call(method, params={}) {return new Promise((resolve,reject)=>{const n=++id;waiting.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});}
async function evaluate(expression) {const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression) {for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timeout: '+expression);}
try {
  await call('Runtime.enable');await call('Network.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:Number(width),height:Number(height),deviceScaleFactor:1,mobile:Number(width)<600});
  await call('Page.navigate',{url});
  await until('typeof lastState !== "undefined" && !!lastState');
  assert.equal(await evaluate('document.documentElement.scrollWidth'),Number(width));
  await evaluate('document.getElementById("all-sessions-btn").click()');
  await until('document.getElementById("v2-content").textContent.includes("Other Claude")');
  assert.equal(await evaluate('Array.from(document.querySelectorAll("#v2-content button")).filter(b=>b.textContent==="End session").length'),1);
  await evaluate('Array.from(document.querySelectorAll("#v2-content button")).find(b=>b.textContent==="Cancel worker").click()');
  await until('document.getElementById("toasts").textContent.includes("Worker stopping")');
  assert.ok(requests.includes('/api/delegate/dlg_active/cancel'));
  await until('Array.from(document.querySelectorAll("#v2-content button")).some(b=>b.textContent==="End session")');
  await evaluate('window.confirm=()=>false;Array.from(document.querySelectorAll("#v2-content button")).find(b=>b.textContent==="End session").click()');
  assert.ok(!requests.some(p=>p.includes('/sessions/')));
  await evaluate('window.confirm=()=>true;Array.from(document.querySelectorAll("#v2-content button")).find(b=>b.textContent==="End session").click()');
  await until('document.getElementById("toasts").textContent.includes("Session ending")');
  assert.ok(requests.some(p=>p.includes('/sessions/')));
  assert.equal(await evaluate('document.documentElement.scrollWidth'),Number(width));
  if(shot){const screenshot=await call('Page.captureScreenshot',{format:'png'});await writeFile(shot,Buffer.from(screenshot.data,'base64'));}
  await evaluate('document.getElementById("v2-close").click();document.getElementById("session-pill").click()');
  await until('!document.getElementById("settings").hidden');
  assert.ok(await evaluate('document.getElementById("notify-btn").textContent.includes("background")'));
  assert.equal(await evaluate('document.documentElement.scrollWidth'),Number(width));
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({width:Number(width),sessions:true,cancel:true,endConfirmation:true,errors}));
} finally {socket.close();}
