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
try{
  await call('Runtime.enable');await call('Network.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url});await until('typeof lastState !== "undefined" && !!lastState');
  await evaluate('clearTimeout(statePollTimer);clearTimeout(statsPollTimer)');
  assert.equal(await evaluate('$(' + JSON.stringify('playbook-current') + ').textContent'),'WISDOM');
  assert.equal(await evaluate('document.querySelectorAll(".exchange-card").length'),3);
  assert.equal(await evaluate('document.querySelectorAll(".exchange-card.arrive").length'),0,'History must not animate as new traffic');
  await shot('desktop');
  // A real HTTP fixture's next generation supplies new hops through the page's consumer.
  await evaluate('getJSON("/api/state").then(applyState)');
  assert.equal(await evaluate('document.querySelectorAll(".exchange-card").length'),3);
  assert.ok(await evaluate('document.querySelectorAll(".exchange-card.arrive").length > 0'), 'New HTTP messages animate');
  assert.equal(await evaluate('(()=>{const previous=$("exchange-list").lastElementChild;applyState(structuredClone(lastState));return previous===$("exchange-list").lastElementChild})()'),true,'Unchanged polling retains cards');
  await evaluate('$("exchange-list").lastElementChild.click()');
  assert.ok(await evaluate('document.querySelector("#feed-inner [data-mid=m_0015]")'), 'Exchange opens its task in the feed');
  await click('session-pill');await click('tab-preferences');
  // Exercise the formerly broken subscribed-device state without registering a device.
  await evaluate('pushDevice="fixture-device";renderPushControls()');
  assert.equal(await evaluate('$("notify-status").textContent'),'Enabled');
  assert.equal(await evaluate('$("notify-btn").hidden'),true);
  await fits('#notify-status, .notification-controls button');
  await shot('desktop-preferences');
  await click('tab-agent');await shot('desktop-setup');
  await evaluate('$("set-vendor").querySelector("[data-value=codex]").click();$("set-model").value="gpt-6-astra";$("set-model").dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('$("set-effort").children.length'),6);
  await evaluate('$("tab-agent").focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
  assert.equal(await evaluate('$("tab-team").getAttribute("aria-selected")'),'true');
  await click('tab-preferences');
  await evaluate('$("animate-traffic").focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab'});
  assert.equal(await evaluate('document.activeElement.id'),'settings-close','Dialog wraps focus');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
  assert.equal(await evaluate('document.activeElement.id'),'session-pill','Closing returns focus');
  await click('playbooks-btn');await until('$("set-playbooks").children.length===3');
  assert.equal(await evaluate('$("set-playbooks").querySelector("input").value'),'wisdom');
  await shot('desktop-library');
  // Invalid file stays local; valid drop uploads but cannot silently change instructions.
  await evaluate('uploadPlaybook(new File(["not markdown"],"bad.txt"))');
  assert.equal(mutations.filter(m=>m.path==='/api/playbooks').length,0);
  await evaluate('(()=>{const dt=new DataTransfer();dt.items.add(new File(["# My instructions\\nCheck the evidence."],"My guide.md",{type:"text/markdown"}));$("playbook-drop").dispatchEvent(new DragEvent("drop",{bubbles:true,dataTransfer:dt}));})()');
  await until('$("upload-status").textContent.includes("is ready")');
  assert.equal(mutations.filter(m=>m.path==='/api/playbooks').length,1);
  assert.equal(mutations.filter(m=>m.path==='/api/orchestrator').length,0,'Upload must not activate');
  await click('playbook-apply');await until('$("playbooks").hidden');
  assert.deepEqual(mutations.find(m=>m.path==='/api/orchestrator').body,{playbook:'uploaded-guide'});
  await until('$("playbook-current").textContent==="My guide"');
  // Cancelling draft agent changes and opening the library must not overwrite the selected playbook.
  await click('session-pill');await click('apply-btn');
  assert.equal(mutations.filter(m=>m.path==='/api/orchestrator').length,1);
  await evaluate('$("set-name").value="Navigator";$("set-name").dispatchEvent(new Event("input"))');
  await click('apply-btn');await until('$("settings").hidden');
  assert.deepEqual(mutations.filter(m=>m.path==='/api/orchestrator')[1].body,{name:'Navigator'},'Agent settings cannot overwrite playbook selection');
  await click('session-pill');
  await click('settings-close');
  await evaluate('$("toasts").textContent=""');
  for(const width of [1000,390,320]){
    await call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:width<600});
    await evaluate('applyTheme("dark");renderGraph(lastState,derived)');
    assert.equal(await evaluate('document.documentElement.scrollWidth'),width);
    await fits('.library-btn, #session-pill, #search-btn, #menu-btn');
    await shot(`${width}-workspace`);
    await click('session-pill');await click('tab-preferences');
    await fits('#notify-status, .notification-controls button, .close-btn');
    assert.equal(await evaluate('$("settings").scrollWidth <= $("settings").clientWidth'),true);
    await shot(`${width}-preferences`);
    await click('tab-agent');
    await fits('#settings-footer, #apply-btn, #set-effort button');
    await shot(`${width}-setup`);
    await click('settings-close');await click('playbooks-btn');
    await fits('#playbook-apply, #playbooks .setup-footer');
    await shot(`${width}-library`);
    await evaluate('applyTheme("light")');await shot(`${width}-library-light`);
    await click('playbooks-close');
  }
  // Busy changes remain staged; no extra calls or silent instruction changes.
  await evaluate('lastState.orchestrator.busy=true');await click('playbooks-btn');
  await evaluate('$("set-playbooks").querySelector("input[value=wisdom]").click()');
  assert.equal(await evaluate('$("playbook-apply").disabled'),true);await click('playbooks-close');
  // Burst of real-shaped messages stays bounded, preserves literal text and settles idle.
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await evaluate('applyTheme("dark");window.beforeBurst=structuredClone(lastState);const burst=Array.from({length:100},(_,i)=>({id:"burst"+i,ts:new Date().toISOString(),from:"orchestrator",to:"worker:codex",kind:"tool_use",text:"<img src=x onerror=alert(1)> Message "+i,meta:{}}));applyState({...lastState,messages:[...lastState.messages,...burst]})');
  assert.equal(await evaluate('document.querySelectorAll(".exchange-card").length'),3);
  assert.ok(await evaluate('cometQueue.length <= 6 && cometsActive <= 6'));
  assert.equal(await evaluate('document.querySelectorAll("#exchange-list img").length'),0);
  assert.ok(await evaluate('$("exchange-list").textContent.includes("Message 99")'));
  await evaluate('graphCollapsed=true;renderGraph(lastState,derived);applyState({...lastState,messages:[...lastState.messages,{id:"collapsed",ts:new Date().toISOString(),from:"worker:codex",to:"orchestrator",kind:"receipt",text:"Hidden graph result",meta:{root_code:"ok"}}]})');
  assert.equal(await evaluate('cometQueue.length'),0,'Collapsed graph discards queued motion');
  assert.equal(await evaluate('$("exchange-list").lastElementChild.classList.contains("arrive")'),false);
  await evaluate('graphCollapsed=false;renderGraph(lastState,derived)');
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  // Assert the visible reduced-motion contract, not CDP's asynchronous matchMedia event delivery.
  await until('reducedMotion.matches');
  await evaluate('applyState({...lastState,messages:[...lastState.messages,{id:"reduced",ts:new Date().toISOString(),from:"worker:codex",to:"orchestrator",kind:"receipt",text:"Reduced motion still shows this result",meta:{root_code:"ok"}}]})');
  assert.equal(await evaluate('Array.from(document.querySelectorAll(".comet, .edge-work, .discwrap .spin")).filter(n=>getComputedStyle(n).display!=="none" && getComputedStyle(n).animationName!=="none").length'),0);
  assert.equal(await evaluate('cometQueue.length'),0);
  assert.equal(await evaluate('getComputedStyle($("exchange-list").lastElementChild).animationName'),'none');
  await evaluate('Object.defineProperty(document,"hidden",{configurable:true,value:true});document.dispatchEvent(new Event("visibilitychange"))');
  assert.equal(await evaluate('cometQueue.length'),0);
  await evaluate('delete document.hidden;document.dispatchEvent(new Event("visibilitychange"));applyState(beforeBurst)');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({layout:[1440,1000,390,320],playbookDrop:true,uploadDoesNotActivate:true,busyGuard:true,focus:true,boundedTraffic:true,reducedMotion:true,errors}));
}finally{socket.close();}
