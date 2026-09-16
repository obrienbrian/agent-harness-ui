"""Durable notifications, endpoint authority, and real encryption without a provider call."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import test_ui as base
from harness_ui.push import Push, validate
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from harness.receipts import now_iso


def subscription(endpoint='https://fcm.googleapis.com/fcm/send/test-device'):
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    enc = lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode()
    return {'endpoint':endpoint, 'keys':{'p256dh':enc(public),'auth':enc(auth)}}, private, auth


class PushProof(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='harness-push-proof-')
        self.root = Path(self.temp.name)
        self.messages = self.root/'messages.jsonl'
        self.calls = []
        self.code = 201
        self.push = self.open()
        self.sub, self.private, self.auth = subscription()
        self.sid = self.push.subscribe(self.sub)['id']

    def open(self):
        def send(sub,payload):
            self.calls.append((sub,json.loads(payload)))
            return self.code
        return Push(root=self.root/'push',config=self.root/'config',messages=self.messages,sender=send)

    def tearDown(self):
        self.push.close(); self.temp.cleanup()

    def event(self, key='m_done', kind='complete'):
        row={'id':key,'ts':now_iso(),'kind':'status','text':'private prompt must never be sent', 'meta':{'notification':kind,'turn_id':'t_demo'}}
        with self.messages.open('a') as f: f.write(json.dumps(row)+'\n')

    def test_collect_restart_retry_and_encryption_privacy(self):
        self.event(); self.push.collect()
        self.assertEqual(self.push.status()['pending'],1)
        self.code=503; self.push.deliver()
        self.assertEqual(self.push.status()['pending'],1)
        self.assertNotIn('private prompt',json.dumps(self.calls))
        self.assertEqual(self.calls[0][1]['url'],'/#turn=t_demo')
        self.push.close(); self.push=self.open()
        self.push.collect()
        self.assertEqual(self.push.status()['pending'],1)
        with self.push.db: self.push.db.execute('UPDATE outbox SET next=0')
        self.code=201; self.push.deliver()
        self.push.collect(); self.push.deliver()
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.push.status()['pending'],0)
        self.assertEqual(self.push.key.stat().st_mode & 0o777,0o600)
        self.assertEqual((self.push.root/'outbox.sqlite3').stat().st_mode & 0o777,0o600)

    def test_question_attention_deep_link_does_not_duplicate_receipt_alert(self):
        q={'id':'m_question','ts':now_iso(),'kind':'question','to':'user','meta':{'notification':'attention','question_id':'q_example','delegation_id':'dlg_example'}}
        rec={'id':'m_question_receipt','ts':now_iso(),'kind':'receipt','to':'user','meta':{'root_code':'HARNESS_NEEDS_INPUT','question_id':'q_example','delegation_id':'dlg_example'}}
        self.messages.write_text(json.dumps(q)+'\n'+json.dumps(rec)+'\n')
        self.push.collect();self.code=201;self.push.deliver()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][1]['url'],'/#questions')
        self.assertEqual(self.calls[0][1]['title'],'Harness needs attention')

    def test_partial_write_direct_receipt_attention_and_expiry(self):
        row={'id':'m_receipt','ts':now_iso(),'kind':'receipt','to':'user','meta':{'root_code':'HARNESS_WORKER_TIMEOUT','delegation_id':'dlg_demo'}}
        value=json.dumps(row)
        self.messages.write_text(value[:10]); self.push.collect()
        self.assertEqual(self.push.status()['pending'],0)
        with self.messages.open('a') as f:f.write(value[10:]+'\n')
        self.push.collect(); self.code=410; self.push.deliver()
        self.assertEqual(self.calls[0][1]['title'],'Harness needs attention')
        self.assertEqual(self.push.status()['subscriptions'],0)
        self.assertEqual(self.push.status()['pending'],0)

    def test_unsubscribe_removes_pending_and_failed_delivery_is_visible(self):
        self.push.test(self.sid);self.code=403;self.push.deliver()
        self.assertEqual(self.push.status()['failed'],1)
        self.push.test(self.sid);self.push.unsubscribe(self.sid);self.push.deliver()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.push.status()['pending'],0)

    def test_endpoint_validation_at_registration_and_delivery(self):
        for endpoint in ('http://fcm.googleapis.com/x','https://127.0.0.1/x','https://fcm.googleapis.com.evil/x','https://evil@fcm.googleapis.com/x','https://fcm.googleapis.com:444/x','https://fcm.googleapis.com/x#bad'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                self.push.subscribe({**self.sub,'endpoint':endpoint})
        for endpoint in ('https://web.push.apple.com/example','https://updates.push.services.mozilla.com/wpush/v2/example'):
            self.assertEqual(validate({**self.sub,'endpoint':endpoint})['endpoint'],endpoint)
        with self.assertRaises(ValueError): self.push.subscribe({**self.sub,'keys':{'auth':'invalid','p256dh':'invalid'}})

    def test_real_webpush_body_decrypts_only_for_subscribed_device_and_no_redirects(self):
        import http_ece
        import requests
        payload=json.dumps({'title':'Test','body':'Open Harness'})
        captured={}
        def post(session,method,url,**kwargs):
            captured.update(kwargs)
            self.assertEqual(url,self.sub['endpoint'])
            self.assertFalse(kwargs['allow_redirects'])
            response=requests.Response();response.status_code=201;response._content=b''
            return response
        with patch('requests.Session.request',post):
            self.assertEqual(self.push.send(self.sub,payload),201)
        self.assertNotIn(payload.encode(),captured['data'])
        self.assertEqual(http_ece.decrypt(captured['data'],private_key=self.private,auth_secret=self.auth,version='aes128gcm').decode(),payload)
        self.assertEqual(captured['timeout'],10)
        self.assertTrue(any(k.lower()=='authorization' for k in captured['headers']))
