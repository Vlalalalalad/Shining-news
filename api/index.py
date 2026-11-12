"""Authenticated Telegram webhook. Settings snapshots live in a private Blob store."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from vercel.blob.sync import get_blob, put_blob, query_blobs

BASE = Path(__file__).resolve().parents[1]
RADAR = BASE / 'Telegram-AI-News-Radar-v1.0'
sys.path.insert(0, str(RADAR))
import control
import radar

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
CONFIG = json.loads((RADAR / 'config.json').read_text(encoding='utf-8'))


def bot_token():
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        sealed = json.loads((RADAR / 'sealed-control-token.json').read_text())
        private = serialization.load_pem_private_key(
            os.environ['CONTROL_PRIVATE_KEY'].encode(), password=None)
        token = private.decrypt(base64.b64decode(sealed['ciphertext']),
                                padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                             algorithm=hashes.SHA256(), label=None))
        os.environ['TELEGRAM_BOT_TOKEN'] = token.decode()
    return os.environ['TELEGRAM_BOT_TOKEN']


def auth_secret():
    return hashlib.sha256((bot_token() + ':control-webhook-v1').encode()).hexdigest()


def authorize(value):
    if not hmac.compare_digest(value or '', auth_secret()):
        raise HTTPException(401, 'Unauthorized')


def load_snapshot():
    # Immutable paths prevent serving stale overwritten settings from a CDN cache.
    snapshots = list(query_blobs(prefix='controls/', page_size=1000))
    if not snapshots:
        return json.loads((RADAR / 'initial-control-state.json').read_text(encoding='utf-8'))
    latest = max(snapshots, key=lambda entry: entry.pathname)
    return json.loads(get_blob(latest.url, access='private').body)


@app.get('/api/health')
def health():
    return {'service': 'shining-news-controls', 'ok': True}


@app.get('/api/settings')
def settings(request: Request):
    authorize(request.headers.get('authorization', '').removeprefix('Bearer '))
    snapshot = load_snapshot()
    return JSONResponse({'settings': snapshot.get('settings', {})},
                        headers={'Cache-Control': 'no-store'})


@app.post('/api/webhook')
async def webhook(request: Request):
    authorize(request.headers.get('x-telegram-bot-api-secret-token'))
    update = await request.json()
    callback = update.get('callback_query')
    message = callback.get('message', {}) if callback else update.get('message', {})
    sender = (callback or message).get('from', {}).get('id')
    chat = message.get('chat', {})
    if chat.get('type') != 'private' or chat.get('id') != sender:
        return {'ok': True}
    if not control.is_admin(sender, CONFIG):
        # /id reports only the sender's own ID; no storage or configuration access.
        if message.get('text', '').strip() == '/id':
            control.handle_update(update, {}, CONFIG)
        return {'ok': True}
    snapshot = load_snapshot()
    update_id = int(update['update_id'])
    processed = snapshot.get('processed_ids')
    if ((processed is None and update_id <= int(snapshot.get('last_update_id', -1)))
            or (processed is not None and update_id in processed)):
        return {'ok': True, 'duplicate': True}
    control.handle_update(update, snapshot, CONFIG)
    snapshot['last_update_id'] = update_id
    snapshot['processed_ids'] = ((processed or []) + [update_id])[-100:]
    put_blob(f'controls/{time.time_ns():020d}-{update_id}.json',
             json.dumps(snapshot, ensure_ascii=False).encode(),
             access='private', content_type='application/json',
             add_random_suffix=False, allow_overwrite=False)
    print('Webhook admin update saved')
    return {'ok': True}
