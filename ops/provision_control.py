"""Run only in GitHub Actions; never prints the bot token."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'Telegram-AI-News-Radar-v1.0'
token = os.environ['TELEGRAM_BOT_TOKEN']
mode = sys.argv[1]
if mode == 'seal':
    encrypted = subprocess.run(
        ['openssl', 'pkeyutl', '-encrypt', '-pubin', '-inkey',
         str(ROOT / 'ops/control-public-key.pem'),
         '-pkeyopt', 'rsa_padding_mode:oaep', '-pkeyopt', 'rsa_oaep_md:sha256'],
        input=token.encode(), capture_output=True, check=True).stdout
    (BASE / 'sealed-control-token.json').write_text(
        json.dumps({'ciphertext': base64.b64encode(encrypted).decode()}) + '\n')
    state = json.loads((BASE / 'state.json').read_text())
    (BASE / 'initial-control-state.json').write_text(json.dumps({
        'settings': state.get('settings', {}),
        'last_update_id': int(state.get('telegram_offset', 0)) - 1
    }, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Bot credential sealed; initial settings copied')
elif mode == 'enable':
    config = json.loads((BASE / 'config.json').read_text())
    url = config['control_webhook_url']
    secret = hashlib.sha256((token + ':control-webhook-v1').encode()).hexdigest()
    # This authenticated read proves decryption AND durable storage work before switching Telegram.
    with urlopen(Request(url.replace('/webhook', '/settings'), headers={
        'Authorization': 'Bearer ' + secret}), timeout=25) as response:
        assert isinstance(json.load(response).get('settings'), dict)
    payload = json.dumps({'url': url, 'secret_token': secret, 'max_connections': 1,
                          'allowed_updates': ['message', 'callback_query'],
                          'drop_pending_updates': False}).encode()
    with urlopen(Request('https://api.telegram.org/bot' + token + '/setWebhook',
                         data=payload, headers={'Content-Type': 'application/json'}), timeout=25) as response:
        assert json.load(response)['ok']
    with urlopen('https://api.telegram.org/bot' + token + '/getWebhookInfo', timeout=25) as response:
        info = json.load(response)['result']
    assert info['url'] == url
    print('Webhook enabled:', info['url'], 'pending:', info['pending_update_count'])
else:
    raise ValueError('Unknown provisioning mode')
