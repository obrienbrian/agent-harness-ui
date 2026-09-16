// Browser-level layout, instruction selection and bounded live-traffic checks.
// Uses Chromium's own protocol; fixture HTTP never invokes a model.
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
const [debug, url, shotDir] = process.argv.slice(2);
const target = (await (await fetch(debug + '/json/list')).json()).find(t => t.type === 'page');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject) => {socket.onopen=resolve;socket.onerror=reject;});
let id=0;
const waiting=new Map(), errors=[], mutations=[];
socket.onmessage=e=>{
  const m=JSON.parse(e.data);
  if(m.id){const p=waiting.get(m.id);waiting.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}
  if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
  if(m.method==='Network.requestWillBeSent' && m.params.request.method==='POST')mutations.push({path:new URL(m.params.request.url).pathname, body:JSON.parse(m.params.request.postData || '{}')});
};
function call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;waiting.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});}
async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,40));}throw new Error('Timeout: '+expression+' '+JSON.stringify(await evaluate('({reduced:reducedMotion.matches,hidden:document.hidden,motion:document.body.className})'))+' '+JSON.stringify(errors));}
async function shot(name){if(!shotDir)return;await mkdir(shotDir,{recursive:true});const s=await call('Page.captureScreenshot',{format:'png'});await writeFile(`${shotDir}/${name}.png`,Buffer.from(s.data,'base64'));}
async function click(id){await evaluate(`document.getElementById(${JSON.stringify(id)}).focus();document.getElementById(${JSON.stringify(id)}).click()`);}
async function fits(selector){
  const bad=await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).filter(n=>n.getClientRects().length).filter(n=>{const r=n.getBoundingClientRect();return r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1 || n.scrollHeight > n.clientHeight+2 && getComputedStyle(n).overflowY === 'visible'}).map(n=>n.id||n.className)`);
  assert.deepEqual(bad,[],`Clipped controls: ${bad}`);
}
async function command(text){await evaluate(`composerInput.value=${JSON.stringify(text)};composerInput.dispatchEvent(new Event('input'));submitComposer()`);}
try{
  await call('Runtime.enable');await call('Network.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await call('Page.navigate',{url});await until('typeof lastState !== "undefined" && !!lastState');
  await evaluate('clearTimeout(statePollTimer);clearTimeout(statsPollTimer)');
  await click('help-btn');
  assert.ok(await evaluate('$("v2-content").textContent.includes("Keep a goal moving")'));
  await fits('#v2-close, .help-tabs button');await shot('phone-help');
  await evaluate('Array.from(document.querySelectorAll(".help-tabs button")).find(b=>b.textContent==="Commands").click()');
  assert.ok(await evaluate('$("v2-content").textContent.includes("/clear [title]")'));
  assert.ok(await evaluate('$("v2-content").textContent.includes("not available here")'));
  await shot('phone-commands');
  await evaluate('Array.from(document.querySelectorAll(".command-row")).find(b=>b.textContent.startsWith("/goal ")).click()');
  assert.equal(await evaluate('composerInput.value'),'/goal ');
  await evaluate('submitComposer()');await until('$("v2-content").textContent.includes("Goal mode is available with Codex")');
  assert.equal(mutations.length,0,'Help and metadata never start work');await click('v2-close');
  await command('/compact');
  assert.equal(await evaluate('composerInput.value'),'/compact');assert.equal(mutations.length,0);
  await evaluate('composerInput.value="/he";composerInput.dispatchEvent(new Event("input"));composerInput.focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab'});
  assert.equal(await evaluate('composerInput.value'),'/help ');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter'});
  await until('$("v2-title").textContent==="Help & instructions" && !$("v2-drawer").hidden');
  await click('v2-close');
  await evaluate('postJSON("/api/orchestrator",{vendor:"codex",model:"gpt-6-astra",effort:"high"}).then(refreshCommandState)');
  await command('/goal');await until('!!$("goal-objective")');
  await evaluate('$("goal-objective").value="Finish the fixture work and verify it";$("goal-budget").value="5000";$("goal-objective").form.requestSubmit()');
  await until('lastState.goal.running && !!$("goal-detail-status")');
  assert.deepEqual(mutations.find(m=>m.path==='/api/goal').body,{action:'set',objective:'Finish the fixture work and verify it',token_budget:5000});
  assert.equal(await evaluate('$("goal-strip").hidden'),false);await click('v2-close');
  await fits('#goal-strip, #goal-toggle, #composer-input');await shot('phone-active-goal');
  await command('/clear');
  assert.equal(await evaluate('composerInput.value'),'/clear','Rejected clear preserves user text');
  assert.ok(await evaluate('lastState.messages.length>0'));
  await evaluate('composerInput.value="/goal pause";composerInput.dispatchEvent(new Event("input"))');
  assert.equal(await evaluate('sendBtn.disabled'),false,'Busy composer permits controls');
  await evaluate('submitComposer()');await until('!lastState.goal.running');
  assert.equal(await evaluate('lastState.goal.goal.status'),'paused');
  await command('/goal edit');await until('!!$("goal-objective")');
  await evaluate('$("goal-objective").value="Revised fixture objective";$("goal-budget").value="";$("goal-objective").form.requestSubmit()');
  await until('lastState.goal.goal.objective==="Revised fixture objective"');
  assert.equal(await evaluate('lastState.goal.goal.tokenBudget'),null);
  await click('v2-close');await command('/goal resume');await until('lastState.goal.running');
  await command('/stop');await until('!lastState.goal.running');
  await command('/goal clear');await until('!lastState.goal.goal');
  assert.equal(await evaluate('$("goal-strip").hidden'),true);
  const count=await evaluate('lastState.messages.length');
  await command('/new');assert.equal(await evaluate('lastState.messages.length'),count);
  await command('/model gpt-5.6-terra');assert.equal(await evaluate('lastState.orchestrator.model'),'gpt-5.6-terra');
  await command('/effort low');assert.equal(await evaluate('lastState.orchestrator.effort'),'low');
  await evaluate('window.beforeClear=structuredClone(lastState)');
  await command('/clear');assert.equal(await evaluate('lastState.messages.length'),0);
  assert.equal(await evaluate('lastState.orchestrator.playbook'),'wisdom');
  await evaluate('applyState(window.beforeClear)');assert.equal(await evaluate('lastState.messages.length'),0,'An older in-flight poll cannot resurrect the feed');
  await evaluate('applyState({...lastState,messages:window.beforeClear.messages})');assert.equal(await evaluate('lastState.messages.length'),0,'Old SSE replay stays below clear boundary');
  await evaluate('applyState({...lastState,messages:[{id:"after_clear",offset:1000000,ts:new Date().toISOString(),from:"user",to:"orchestrator",kind:"prompt",text:"After clear",meta:{}}]})');
  assert.equal(await evaluate('lastState.messages.length'),1);
  await command('/theme light');assert.equal(await evaluate('document.documentElement.dataset.theme'),'light');
  for(const width of [320,1440]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<500});
    await click('help-btn');await fits('#help-btn, #v2-close, .help-tabs button');
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'));
    await shot(width+'-help');await click('v2-close');
  }
  await command('//literal prompt');assert.equal(mutations.filter(m=>m.path==='/api/say').length,1);
  assert.equal(mutations.find(m=>m.path==='/api/say').body.text,'//literal prompt');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({help:true,commands:true,goalLifecycle:true,busyControls:true,clearBoundary:true,layouts:[390,320,1440],noModelPromptsForCommands:true,errors}));
}finally{socket.close();}
