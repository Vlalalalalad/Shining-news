"""Webhook auth, dedupe and durable command checks; no Telegram requests."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('webhook_app', ROOT / 'api/index.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class WebhookTests(unittest.TestCase):
    def test_auth_dedupe_and_admin_settings(self):
        config = {**web.CONFIG, 'admin_user_hashes': [hashlib.sha256(b'100').hexdigest()]}
        snapshot = {'settings': {}, 'last_update_id': 5}
        update = {'update_id': 6, 'message': {'from': {'id': 100},
                  'chat': {'id': 100, 'type': 'private'}, 'text': '/limit 7'}}
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'fake'}), \
             patch.object(web, 'CONFIG', config), \
             patch.object(web, 'load_snapshot', return_value=snapshot) as read, \
             patch.object(web, 'put_blob') as write, \
             patch.object(web.control, 'send_private') as send:
            client = TestClient(web.app)
            self.assertEqual(client.post('/api/webhook', json=update).status_code, 401)
            read.assert_not_called()
            headers = {'X-Telegram-Bot-Api-Secret-Token': web.auth_secret()}
            self.assertEqual(client.post('/api/webhook', json=update, headers=headers).status_code, 200)
            self.assertEqual(snapshot['settings']['max_regular_per_day'], 7)
            write.assert_called_once()
            send.assert_called_once()
            self.assertTrue(client.post('/api/webhook', json=update, headers=headers).json()['duplicate'])
            self.assertEqual(send.call_count, 1)
            update['message']['from']['id'] = 200
            update['message']['chat']['id'] = 200
            client.post('/api/webhook', json=update, headers=headers)
            self.assertEqual(write.call_count, 1)


if __name__ == '__main__':
    unittest.main()
