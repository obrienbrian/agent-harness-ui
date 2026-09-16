// Browser-level checks for the COLLAB-01 UI slice: neutral AI Kernel copy, session titles,
// and the questions inbox (options + free text, draft preservation, busy/error handling,
// graph/roster attribution). Uses Chromium's own protocol; fixture HTTP never invokes a model.
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
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,40));}throw new Error('Timeout: '+expression+' '+JSON.stringify(errors));}
async function shot(name){if(!shotDir)return;await new Promise(r=>setTimeout(r,300));await mkdir(shotDir,{recursive:true});const s=await call('Page.captureScreenshot',{format:'png'});await writeFile(`${shotDir}/${name}.png`,Buffer.from(s.data,'base64'));}
async function click(elId){await evaluate(`document.getElementById(${JSON.stringify(elId)}).focus();document.getElementById(${JSON.stringify(elId)}).click()`);}
async function fits(selector){
  const bad=await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).filter(n=>n.getClientRects().length).filter(n=>{const r=n.getBoundingClientRect();return r.left < -1 || r.right > innerWidth+1 || r.top < -1 || r.bottom > innerHeight+1 || n.scrollHeight > n.clientHeight+2 && getComputedStyle(n).overflowY === 'visible'}).map(n=>n.id||n.className)`);
  assert.deepEqual(bad,[],`Clipped controls: ${bad}`);
}
async function command(text){await evaluate(`composerInput.value=${JSON.stringify(text)};composerInput.dispatchEvent(new Event('input'));submitComposer()`);}
const mutationsTo = (path) => mutations.filter((m) => m.path === path);
async function untilLocal(predicate){for(let i=0;i<100;i++){if(predicate())return;await new Promise(r=>setTimeout(r,40));}throw new Error('Timeout waiting for local condition');}

try{
  await call('Runtime.enable');await call('Network.enable');await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await call('Page.navigate',{url});await until('typeof lastState !== "undefined" && !!lastState');
  await evaluate('clearTimeout(statePollTimer);clearTimeout(statsPollTimer)');

  // ---- neutral AI Kernel copy (WISDOM is an included example, not a special brand) ----
  assert.equal(await evaluate('document.getElementById("playbooks-btn").title'),'AI Kernel library');
  assert.equal(await evaluate('document.querySelector(".library-caption").textContent'),'Kernels');
  assert.equal(await evaluate('!!document.querySelector("#playbooks-btn .library-mark svg")'),true,'Neutral icon replaces the W mark');
  assert.equal(await evaluate('document.querySelector("#playbooks-btn .library-mark").textContent.trim()'),'','No WISDOM-specific letter mark');
  await click('playbooks-btn'); await until('$("set-playbooks").children.length>0');
  assert.equal(await evaluate('$("playbooks-title").textContent'),'AI Kernel library');
  assert.equal(await evaluate('document.querySelector("#playbooks .panel-intro").textContent'),'Choose the instructions your agents work from. Use an included kernel or upload your own markdown.');
  assert.equal(await evaluate('document.querySelector(".status-tag.on").textContent'),'Included','Default badge is now Included');
  assert.equal(await evaluate('$("playbook-apply").textContent'),'Currently in use');
  await shot('kernel-library');
  await click('playbooks-close');

  // /kernel is the preferred command; /playbook keeps working as a hidden legacy alias.
  await command('/help');await until('$("v2-title").textContent==="Help & instructions"');
  await evaluate('Array.from(document.querySelectorAll(".help-tabs button")).find(b=>b.textContent==="Commands").click()');
  const commandsText = await evaluate('$("v2-content").textContent');
  assert.ok(commandsText.includes('/kernel'),'Preferred /kernel command is advertised');
  assert.ok(!commandsText.includes('/playbook'),'/playbook stays a hidden legacy alias, not advertised');
  await click('v2-close');
  await command('/kernel'); await until('!$("playbooks").hidden');
  await click('playbooks-close');
  await command('/playbook'); await until('!$("playbooks").hidden');
  assert.equal(await evaluate('composerInput.value'),'','Recognized alias command clears the composer');
  await click('playbooks-close');

  // ---- session titles: separate from the agent's display name ----
  await click('session-pill'); await until('!$("settings").hidden');
  assert.equal(await evaluate('$("set-session-title").placeholder'),'Untitled session');
  assert.equal(await evaluate('$("set-name").value'),'Orchestrator','Agent display name field is unaffected');
  await evaluate('$("set-session-title").value="Rollback review";$("set-session-title").dispatchEvent(new Event("input"))');
  await click('apply-btn'); await until('$("settings").hidden');
  assert.deepEqual(mutationsTo('/api/orchestrator').at(-1).body,{session_title:'Rollback review'},'Only the title changes; agent name/vendor untouched');
  assert.equal(await evaluate('$("session-title-btn").textContent'),'Rollback review');
  assert.equal(await evaluate('$("pill-name").textContent'),'Fable','Agent identity (e.g. Astra) stays separate from the session title');
  await shot('session-title-header');

  await command('/rename Launch prep');
  await until('lastState.orchestrator.session_title==="Launch prep"');
  assert.equal(await evaluate('$("session-title-btn").textContent'),'Launch prep');

  await command('/clear Q3 wrapup');
  await until('lastState.orchestrator.session_title==="Q3 wrapup"');
  assert.deepEqual(mutationsTo('/api/clear').at(-1).body,{clear_view:true, name:'Q3 wrapup'},'/clear <title> sends the wire-compatible name field, not the agent name');
  assert.equal(await evaluate('$("session-title-btn").textContent'),'Q3 wrapup');

  await evaluate('$("session-title-btn").click()');
  await until('!$("settings").hidden && document.activeElement.id==="set-session-title"');
  await click('settings-close');

  // ---- questions inbox: no fabricated answers, real attribution, resolved history retained ----
  const openQ = {id:'q_region', question:'Which region should receive the report?', context:'The task did not name a region.',
    options:['East','West'], status:'open', delegation_id:'dlg_region', source_agent:'worker:codex', session_id:'fixture-session',
    created_at:new Date().toISOString(), answer:null, delivery:null};
  const answeredQ = {id:'q_deploy', question:'Confirm the deploy window?', context:'', options:[], status:'answered',
    delegation_id:null, source_agent:'orchestrator', session_id:'fixture-session', created_at:new Date().toISOString(),
    answer:'Yes, proceed Friday evening.', delivery:{status:'started', kind:'turn', id:'t_answer_deploy'}};
  await evaluate(`applyState({...lastState, questions:[${JSON.stringify(openQ)}, ${JSON.stringify(answeredQ)}]})`);
  assert.equal(await evaluate('$("questions-strip").hidden'),false);
  assert.ok(await evaluate('$("questions-title").textContent.includes("1 question")'));
  assert.ok(await evaluate('$("questions-meta").textContent.includes("Sol")'),'Attributed to the real worker name, not a generic label');
  await fits('.questions-strip');
  await shot('questions-strip');

  // Graph and roster surface the same real pending question, no fabricated activity.
  assert.equal(await evaluate('document.querySelector(\'.node[data-id="worker:codex"]\').classList.contains("has-question")'),true);
  assert.equal(await evaluate('Array.from(document.querySelectorAll("#roster .row")).find(r=>r.dataset.id==="worker:codex").querySelector(".chip.warn")?.textContent'),'?');

  await click('questions-open'); await until('$("v2-title").textContent==="Questions"');
  assert.ok(await evaluate('$("questions-open-list").textContent.includes("Which region should receive the report?")'));
  assert.ok(await evaluate('$("questions-open-list").textContent.includes("The task did not name a region.")'));
  assert.equal(await evaluate('document.querySelectorAll("#questions-open-list .question-options .tchip").length'),2);
  assert.ok(await evaluate('$("questions-resolved-list").textContent.includes("You answered: Yes, proceed Friday evening.")'),'Resolved questions retain their answer and history');
  await shot('questions-drawer');

  // Options AND free text are both available; picking an option fills, never fabricates, a draft.
  await evaluate('document.querySelector("#questions-open-list .question-options .tchip").click()');
  assert.equal(await evaluate('document.querySelector("#questions-open-list textarea").value'),'East');
  await evaluate('const t=document.querySelector("#questions-open-list textarea");t.focus();t.value="East, and notify the regional lead";t.dispatchEvent(new Event("input"))');
  // A background poll must never rewrite text the human is actively typing.
  await evaluate('applyState(structuredClone(lastState))');
  assert.equal(await evaluate('document.querySelector("#questions-open-list textarea").value'),'East, and notify the regional lead','Draft survives a poll while focused');
  assert.equal(await evaluate('document.activeElement === document.querySelector("#questions-open-list textarea")'),true,'Polling preserves typing focus');

  // No backend question exists yet for this id in the fixture; the resulting error must
  // preserve the draft and explain itself rather than silently discarding the answer.
  await evaluate('document.querySelector("#questions-open-list form").requestSubmit()');
  await until('$("toasts").textContent.includes("send answer") || $("toasts").textContent.includes("send yet")');
  assert.ok(mutationsTo('/api/questions/q_region/answer').length>0);
  assert.equal(await evaluate('document.querySelector("#questions-open-list textarea").value'),'East, and notify the regional lead','Draft preserved after a failed send');
  await evaluate('$("toasts").textContent=""');

  // Busy disables answering with an explanation; nothing is answered for the user.
  await evaluate('applyState({...lastState, orchestrator:{...lastState.orchestrator, busy:true}})');
  assert.equal(await evaluate('document.querySelector("#questions-open-list form button[type=submit]").disabled'),true);
  assert.ok(await evaluate('document.querySelector("#questions-open-list .question-form .hint").textContent.length>0'));
  await evaluate('applyState({...lastState, orchestrator:{...lastState.orchestrator, busy:false}})');
  assert.equal(await evaluate('document.querySelector("#questions-open-list form button[type=submit]").disabled'),false);

  // Cancelling asks the server, never fabricates a resolution locally.
  await evaluate('document.querySelector("#questions-open-list .actions .btn.secondary").click()');
  await untilLocal(() => mutationsTo('/api/questions/q_region/cancel').length > 0);
  await shot('questions-busy');
  await click('v2-close');

  // ---- real HARNESS_NEEDS_INPUT receipts link straight into the same inbox ----
  await evaluate(`applyState({...lastState, messages:[...lastState.messages,
    {id:'m_ask_1', offset:9000001, ts:new Date().toISOString(), from:'orchestrator', to:'worker:codex', kind:'tool_use', text:'Draft the report.', meta:{tool:'delegate', class:'readonly', turn_id:'t_ask'}},
    {id:'m_ask_2', offset:9000002, ts:new Date().toISOString(), from:'worker:codex', to:'orchestrator', kind:'receipt', text:'Which region should receive the report?', meta:{root_code:'HARNESS_NEEDS_INPUT', delegation_id:'dlg_region', question_id:'q_region', duration_ms:1200}}
  ]})`);
  await until('document.querySelector("[data-mid=m_ask_1]")');
  assert.ok(await evaluate('document.querySelector("[data-mid=m_ask_1]").textContent.includes("needs your input")'));
  assert.equal(await evaluate('document.querySelector("[data-mid=m_ask_1]").classList.contains("ask")'),true);
  await evaluate('Array.from(document.querySelectorAll("[data-mid=m_ask_1] .acts button")).find(b=>b.textContent==="Answer this question").click()');
  await until('$("v2-title").textContent==="Questions"');
  assert.equal(await evaluate('document.querySelector(\'[data-id="q_region"]\').classList.contains("hl")'),true,'Jumping in highlights the linked question');
  await click('v2-close');

  // ---- resolving the question removes graph/roster attribution ----
  await evaluate(`applyState({...lastState, questions:lastState.questions.map(q=>q.id==='q_region'?{...q,status:'answered',answer:'East'}:q)})`);
  assert.equal(await evaluate('document.querySelector(\'.node[data-id="worker:codex"]\').classList.contains("has-question")'),false);
  assert.equal(await evaluate('$("questions-strip").hidden'),true,'Strip disappears once nothing is open');

  // ---- mobile + reduced motion ----
  await evaluate(`applyState({...lastState, questions:[${JSON.stringify(openQ)}]})`);
  for (const width of [390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
    assert.equal(await evaluate('document.documentElement.scrollWidth'),width);
    await fits('.questions-strip, #questions-open, #questions-toggle');
    await click('questions-open'); await until('$("v2-title").textContent==="Questions"');
    await fits('#questions-open-list .question-card, #questions-open-list textarea, #questions-open-list .btn');
    await shot(`${width}-questions`);
    await click('v2-close');
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await until('reducedMotion.matches');
  await evaluate(`applyState({...lastState, questions:[${JSON.stringify(openQ)}]})`);
  assert.equal(await evaluate('getComputedStyle(document.querySelector(\'[data-id="worker:codex"] .discwrap .ask\')).animationName'),'none','Reduced motion stops the ask pulse');
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});

  // Complete a server-owned question through HTTP, including duplicate-click admission.
  await evaluate('getJSON("/api/state").then(applyState)');
  await click('questions-toggle');
  await until('!!document.querySelector(\'[data-id="q_http"] form\')');
  await shot('inbox');
  await evaluate('(()=>{const card=document.querySelector(\'[data-id="q_http"]\');card.querySelectorAll(".tchip")[1].click();const form=card.querySelector("form");form.requestSubmit();form.requestSubmit();})()');
  await until('lastState.questions.find(q=>q.id==="q_http").status==="answered"');
  assert.equal(await evaluate('lastState.questions.find(q=>q.id==="q_http").answer'),'West');
  assert.equal(mutationsTo('/api/questions/q_http/answer').length,1,'Double click submits once');
  assert.ok(await evaluate('$("questions-resolved-list").textContent.includes("Continuation started")'));
  await evaluate('document.querySelector(\'[data-id="q_http_cancel"] .actions .btn.secondary\').click()');
  await until('lastState.questions.find(q=>q.id==="q_http_cancel").status==="cancelled"');
  await evaluate('applyState({...lastState,questions:lastState.questions.map(q=>q.id==="q_http"?{...q,delivery:{status:"dispatching"}}:q)})');
  assert.ok(await evaluate('$("questions-resolved-list").textContent.includes("Continuation not confirmed")'));
  await click('v2-close');
  await evaluate('location.hash="questions"');
  await until('$("v2-title").textContent==="Questions" && !$("v2-drawer").hidden');

  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({kernelCopy:true,sessionTitles:true,questionsInbox:true,draftPreserved:true,busyGuard:true,needsInputLink:true,mobile:[390,320],reducedMotion:true,errors}));
}finally{socket.close();}
