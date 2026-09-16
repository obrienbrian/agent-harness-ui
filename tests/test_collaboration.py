"""Real HTTP → vendor process → stdio MCP → worker → inbox → resumed process.

Vendor leaf programs are deterministic; no subscription capacity is used.
"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from . import test_ui as base
from harness import questions, receipts, orchestrator as orch, mcp

STUB = r'''#!/usr/bin/env python3
import json, os, sys, subprocess
from pathlib import Path
args = sys.argv[1:]
codex = Path(sys.argv[0]).name == 'codex-questions'
prompt = args[-1] if codex else args[args.index('-p') + 1]
worker = '-o' in args if codex else args[args.index('--output-format') + 1] == 'json'
sid = ('worker-' if worker else 'orchestrator-') + ('codex' if codex else 'claude')
def call(name, arguments):
    payload = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':arguments}}
    done = subprocess.run([os.environ['COLLAB_HARNESS'], 'mcp-serve'], input=json.dumps(payload)+'\n', text=True, capture_output=True, check=True)
    result = json.loads(done.stdout)['result']
    assert not result.get('isError'), result
    return result['structuredContent']
if worker:
    resumed = 'resume' in args if codex else '--resume' in args
    result = 'ANSWER_SEEN: ' + prompt if resumed else json.dumps({'harness_question':{'question':'Which region should receive the report?', 'context':'The task names no region.', 'options':['East','West']}})
else:
    if 'saved clarification' in prompt:
        data = json.loads(prompt.split('The user answered a saved clarification.\n',1)[1].split('\n')[0])
        result = call('delegate_resume', {'id':data['delegation_id'], 'prompt':data['answer']})['result_text']
    elif 'DIRECT_QUESTION' in prompt:
        call('ask_user', {'question':'Choose a release label?', 'options':['Alpha','Beta']})
        result = 'Waiting for your release label.'
    else:
        receipt = call('delegate', {'to':'codex' if codex else 'claude', 'prompt':'REQUEST_REVIEW', 'class':'readonly','cwd':os.getcwd()})
        assert receipt['root_code'] == 'HARNESS_NEEDS_INPUT', receipt
        q = call('ask_user', {'question':receipt['question']['question'], 'context':'This choice belongs to you.', 'options':['East','West'], 'delegation_id':receipt['id']})
        result = 'Waiting for the saved question ' + q['id']
if codex:
    print(json.dumps({'type':'thread.started','thread_id':sid}))
    print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':result}}))
    print(json.dumps({'type':'turn.completed','usage':{}}))
    if worker: Path(args[args.index('-o')+1]).write_text(result)
else:
    if not worker: print(json.dumps({'type':'system','session_id':sid}))
    print(json.dumps({'type':'result','is_error':False,'result':result,'session_id':sid}))
'''


def setUpModule():
    base.setUpModule()
    os.environ['COLLAB_HARNESS'] = str(base.CORE / 'bin/harness')
    for vendor in ('claude', 'codex'):
        p = base.TMP / (vendor + '-questions')
        p.write_text(STUB)
        p.chmod(0o700)
        os.environ['HARNESS_' + vendor.upper() + '_BIN'] = str(p)
    (base.TMP / 'codex-home').mkdir(exist_ok=True)
    (base.TMP / 'codex-home/harness-worker.config.toml').write_text('[mcp_servers.harness]\nenabled = false\n')


def tearDownModule():
    base.tearDownModule()


class Collaboration(unittest.TestCase):
    def setUp(self):
        with questions.database(write=True) as db, db:
            db.execute('DELETE FROM questions')
        cfg, err = orch.update_cfg({'vendor':'claude','model':'sonnet','effort':'low','cwd':str(base.TMP),'reset':True,'session_title':'Release planning'})
        self.assertIsNone(err)

    def ask(self, **extra):
        result = mcp.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'ask_user', 'arguments':{'question':'Which region?', 'options':['East','West'], **extra}}})
        self.assertFalse(result['result']['isError'])
        return result['result']['structuredContent']

    def test_both_vendors_escalate_and_deliver_exact_answer_to_original_worker(self):
        for vendor, model in (('claude','sonnet'), ('codex','gpt-5.6-sol')):
            with self.subTest(vendor=vendor):
                orch.update_cfg({'vendor':vendor,'model':model,'effort':'low','reset':True})
                status, start = base.call('POST','/api/say', {'text':'REQUEST_REVIEW'})
                self.assertEqual(status,202,start)
                turn = base.wait_turn(start['turn_id'])
                self.assertEqual(turn['status'],'done',turn)
                rows = base.call('GET','/api/questions')[1]['questions']
                q = next(q for q in rows if q['status']=='open' and q['session_id']==orch.load_cfg()['session_id'])
                self.assertEqual(q['source_agent'],'worker:'+vendor)
                self.assertEqual(q['worker_question']['question'],'Which region should receive the report?')
                self.assertEqual(q['turn_id'], start['turn_id'])
                rec = receipts.load_receipt(q['delegation_id'])
                self.assertEqual(rec['root_code'],'HARNESS_NEEDS_INPUT')
                status, answered = base.call('POST','/api/questions/'+q['id']+'/answer', {'answer':'West, including the coast'})
                self.assertEqual(status,202,answered)
                result = base.wait_turn(answered['delivery']['id'])
                self.assertEqual(result['status'],'done',result)
                child = next(r for r in receipts.ledger_tail(100) if r.get('resumed_from')==rec['id'])
                self.assertEqual(child['session_ref'],rec['session_ref'])
                self.assertIn('ANSWER_SEEN:',child['result_text'])
                self.assertIn('West, including the coast',child['result_text'])
                count = len(receipts.ledger_tail(100))
                self.assertEqual(base.call('POST','/api/questions/'+q['id']+'/answer',{'answer':'East'})[0],409)
                self.assertEqual(len(receipts.ledger_tail(100)),count)

    def test_orchestrator_can_answer_worker_without_interrupting_user(self):
        context = json.dumps({'session_id':orch.load_cfg()['session_id'], 'permissions':'full-access', 'playbook':'none'})
        with patch.dict(os.environ, {'HARNESS_TURN_ID':'t_confident', 'HARNESS_TURN_CONTEXT':context}):
            result = mcp.call_tool('delegate', {'to':'claude', 'prompt':'REQUEST_REVIEW', 'cwd':str(base.TMP)})
            rec = result['structuredContent']
            self.assertFalse(result['isError'])
            self.assertEqual(rec['root_code'],'HARNESS_NEEDS_INPUT')
            self.assertEqual(questions.listing(audience='user'),[])
            follow = mcp.call_tool('delegate_resume', {'id':rec['id'], 'prompt':'East, as specified in the task'})
        self.assertEqual(follow['structuredContent']['root_code'],'ok')
        q = questions.get(rec['question_id'])
        self.assertEqual(q['status'],'answered')
        self.assertEqual(q['answered_by'],'orchestrator')
        self.assertEqual(q['delivery']['id'],follow['structuredContent']['id'])

    def test_goal_pauses_on_human_question_without_starting_another_turn(self):
        from unittest.mock import MagicMock
        orch.update_cfg({'vendor':'codex','model':'gpt-5.6-sol','effort':'low'})
        cfg=orch.load_cfg()
        cfg['session_ref']={'kind':'codex_thread','id':'goal-question-thread'}
        cfg['goal']={'threadId':'goal-question-thread','status':'active','objective':'Ask a question'}
        orch.save_cfg(cfg)
        tid=orch.REGISTRY.start()
        orch.REGISTRY.turns[tid]['goal_managed']=True
        client=MagicMock()
        client.__enter__.return_value=client
        client.get.return_value=dict(cfg['goal'])
        client.set.return_value={**cfg['goal'],'status':'paused'}
        with patch('harness.codex_goals.Client',return_value=client), patch.object(orch,'_start_turn',side_effect=AssertionError('must pause for the human')):
            orch._run_goal_turn(tid,cfg,'DIRECT_QUESTION')
        client.set.assert_called_once_with('goal-question-thread',status='paused')
        self.assertEqual(orch.load_cfg()['goal']['status'],'paused')
        self.assertFalse(orch._goal_running)

    def test_busy_and_changed_session_do_not_consume_answer(self):
        q = self.ask()
        with patch.object(orch.REGISTRY,'busy',return_value=True):
            self.assertEqual(base.call('POST','/api/questions/'+q['id']+'/answer',{'answer':'East'})[0],409)
        self.assertEqual(questions.get(q['id'])['status'],'open')
        orch.end_session()
        self.assertEqual(base.call('POST','/api/questions/'+q['id']+'/answer',{'answer':'West'})[0],409)
        self.assertIsNone(questions.get(q['id'])['answer'])
        self.assertEqual(base.call('POST','/api/questions/'+q['id']+'/cancel',{})[0],200)

    def test_restart_reads_questions_without_automatic_model_calls(self):
        q = self.ask()
        cfg = orch.load_cfg()
        done = subprocess.run([sys.executable,'-c','from harness.questions import listing; import json; print(json.dumps(listing(audience="user")))'], cwd=base.CORE, capture_output=True,text=True,check=True)
        restored = json.loads(done.stdout)
        self.assertEqual(restored[0]['id'],q['id'])
        self.assertEqual(restored[0]['status'],'open')
        row = questions.get(q['id']); row.update(status='answered', answer='West', delivery={'status':'dispatching'}); questions.save(row)
        self.assertEqual(base.call('POST','/api/questions/'+q['id']+'/answer',{'answer':'West'})[0],409)
        self.assertEqual(orch.load_cfg(),cfg)

    def test_titles_do_not_reset_agent_or_vendor_session_and_history_is_named(self):
        status, start = base.call('POST','/api/say',{'text':'DIRECT_QUESTION'})
        self.assertEqual(status,202,start)
        base.wait_turn(start['turn_id'])
        before = orch.load_cfg()
        status, cfg = base.call('POST','/api/orchestrator',{'session_title':'September rollout'})
        self.assertEqual(status,200,cfg)
        self.assertEqual(cfg['name'],before['name'])
        self.assertEqual(cfg['session_ref'],before['session_ref'])
        self.assertEqual(cfg['session_id'],before['session_id'])
        self.assertEqual(orch.load_cfg().get('revision'),before.get('revision'))
        old = next(r for r in base.call('GET','/api/turns')[1]['turns'] if r['turn_id']==start['turn_id'])
        self.assertEqual(old['session_title'],'September rollout')
        status, _ = base.call('POST','/api/clear',{'name':'Next release'})
        self.assertEqual(status,200)
        self.assertEqual(orch.load_cfg()['session_title'],'Next release')
        self.assertEqual(orch.load_cfg()['name'],before['name'])
        self.assertNotEqual(orch.load_cfg()['session_id'],before['session_id'])
        self.assertEqual(next(r for r in orch.turn_history() if r['turn_id']==start['turn_id'])['session_title'],'September rollout')

    def test_invalid_question_and_title_rejected_and_kernel_alias_round_trip(self):
        for value in ('x'*81, None, 'bad\x00title'):
            self.assertEqual(base.call('POST','/api/orchestrator',{'session_title':value})[0],400)
        with self.assertRaises(ValueError): questions.ask_user({'question':'?', 'options':['same','same']})
        q = self.ask()
        self.assertEqual(base.call('POST','/api/questions/'+q['id']+'/answer',{'answer':' '})[0],400)
        st, uploaded = base.call('POST','/api/kernels',{'name':'Plain review','content':'# Review\nCheck the result.'})
        self.assertEqual(st,201,uploaded)
        self.assertEqual(base.call('POST','/api/orchestrator',{'kernel':uploaded['slug']})[0],200)
        state = base.call('GET','/api/state')[1]
        self.assertEqual(state['orchestrator']['kernel'],'plain-review')
        self.assertEqual(state['orchestrator']['playbook'],'plain-review')
        self.assertTrue(any(k['slug']=='plain-review' for k in state['kernels']))

    def test_inbox_read_is_bounded_and_restorable_with_large_closed_history(self):
        import shutil
        times=[]
        current=self.ask()
        for count in (1000, 10000):
            with questions.database(write=True) as db, db:
                for i in range(count):
                    q={**current,'id':'q_history_'+str(i),'status':'answered','answer':'East','created_at':'2020-01-01T00:00:00+00:00'}
                    db.execute('INSERT OR REPLACE INTO questions VALUES(?,?,?,?,?)',(q['id'],'user','answered',q['created_at'],json.dumps(q)))
                plan=db.execute("EXPLAIN QUERY PLAN SELECT payload FROM questions WHERE audience='user' AND status='answered' ORDER BY created_at DESC LIMIT 100").fetchall()
                self.assertTrue(any('USING INDEX inbox' in r[-1] for r in plan),plan)
            before={p.name:p.stat().st_size for p in questions.STATE_DIR.glob('questions.sqlite3*')}
            started=time.monotonic()
            status,body=base.call('GET','/api/questions')
            times.append({'closed_rows':count,'seconds':time.monotonic()-started,'returned':len(body['questions'])})
            self.assertEqual(status,200)
            self.assertEqual(len(body['questions']),101)
            self.assertIn(current['id'],[q['id'] for q in body['questions']])
            self.assertEqual({p.name:p.stat().st_size for p in questions.STATE_DIR.glob('questions.sqlite3*')},before)
        self.assertLess(max(t['seconds'] for t in times),1.0)
        restored=base.TMP/'restored-questions';restored.mkdir(exist_ok=True)
        # No active transactions: a clean closed rollback-journal DB is a coherent backup.
        shutil.copy2(questions.STATE_DIR/'questions.sqlite3',restored/'questions.sqlite3')
        with patch.object(questions,'STATE_DIR',restored):
            self.assertEqual(questions.get(current['id'])['question'],'Which region?')
            self.assertEqual(len(base.call('GET','/api/questions')[1]['questions']),101)
        if os.environ.get('HARNESS_TEST_EVIDENCE'):
            Path(os.environ['HARNESS_TEST_EVIDENCE']).write_text(json.dumps({'store':str(questions.STATE_DIR),'inbox_samples':times},indent=2))

    def test_direct_worker_question_resumes_worker_without_orchestrator(self):
        status, started = base.call('POST','/api/delegate',{'to':'claude','class':'readonly','prompt':'REQUEST_REVIEW','cwd':str(base.TMP)})
        self.assertEqual(status,202)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rows=questions.listing(audience='user')
            if rows and receipts.load_receipt(started['id']): break
            time.sleep(.02)
        q=rows[0]
        self.assertIsNone(q['turn_id'])
        status, answered=base.call('POST','/api/questions/'+q['id']+'/answer',{'answer':'East'})
        self.assertEqual(status,202,answered)
        self.assertEqual(answered['delivery']['kind'],'delegation')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rec=receipts.load_receipt(answered['delivery']['id'])
            if rec: break
            time.sleep(.02)
        self.assertEqual(rec['root_code'],'ok')
        self.assertIn('East',rec['result_text'])
        self.assertEqual(rec['resumed_from'],started['id'])


if __name__=='__main__': unittest.main()
