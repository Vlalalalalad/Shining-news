#!/usr/bin/env python3
"""Private Telegram command handler and radar settings synchronization."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re

import radar


def telegram(method, payload):
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN missing')
    result = radar.json_request(f'https://api.telegram.org/bot{token}/{method}', payload)
    if not result.get('ok'):
        raise RuntimeError(f'Telegram {method} rejected request')
    return result['result']


def send_private(chat_id, text, keyboard=None, inline=False, remove_keyboard=False):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
               'link_preview_options': {'is_disabled': True}}
    if remove_keyboard:
        payload['reply_markup'] = {'remove_keyboard': True}
    elif keyboard and inline:
        payload['reply_markup'] = {'inline_keyboard': keyboard}
    elif keyboard:
        payload['reply_markup'] = {'keyboard': keyboard, 'resize_keyboard': True}
    telegram('sendMessage', payload)
    print('Control: private reply delivered')


def is_admin(user_id, config):
    if not isinstance(user_id, int):
        return False
    digest = hashlib.sha256(str(user_id).encode('ascii')).hexdigest()
    return any(hmac.compare_digest(digest, expected)
               for expected in config.get('admin_user_hashes', [])
               if isinstance(expected, str) and len(expected) == 64)


def settings_view(state, config):
    from control_ui import view
    return view(state, config)


def migrate_control_state(state):
    # Apply the owner's requested 100% advertising once; later edits stay editable.
    if state.get('advertising_policy_version', 0) < 2:
        state.setdefault('settings', {})['branding_percent'] = 100
        state['advertising_policy_version'] = 2
    return state


def update_setting(settings, name, value):
    from settings_schema import validate
    value = validate(name, value)
    if name == 'branding_text' and value:
        if not radar.russian_copy(value.replace('FINDOLLAR', '')):
            raise ValueError('Рекламний текст має бути російською.')
        if re.search(r'https?://|<|>', value, re.I):
            raise ValueError('Надішліть текст без URL або HTML; посилання бренду налаштовується окремо.')
    settings[name] = value
    if name == 'branding_text':
        settings['branding_mode'] = 'custom' if value else 'auto'


def apply_command(text, settings, config=None):
    from settings_schema import ALIASES, validate
    parts = text.strip().split(maxsplit=1)
    if not parts:
        raise ValueError('Оберіть параметр у меню.')
    command = parts[0].split('@')[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ''
    if command == '/news' and value in ('on', 'off'):
        update_setting(settings, 'news_enabled', value)
    elif command == '/brand' and value in ('auto', 'custom', 'off'):
        if value == 'custom' and not settings.get('branding_text'):
            raise ValueError('Спочатку задайте власний текст у розділі реклами.')
        settings['branding_mode'] = value
    elif command == '/brandtext':
        update_setting(settings, 'branding_text', value)
    elif command.lstrip('/') in ALIASES:
        update_setting(settings, ALIASES[command[1:]], value)
    elif command == '/set':
        args = value.split(maxsplit=1)
        if not args:
            raise ValueError('Оберіть параметр у розширених налаштуваннях.')
        update_setting(settings, args[0], args[1] if len(args) > 1 else '')
    elif command == '/market':
        args = value.split()
        if len(args) not in (3, 4) or args[0].upper() not in ('BTC', 'ETH', 'SOL') or args[1] not in ('1h', '24h'):
            raise ValueError('Оберіть монету, період та параметр у меню цінових алертів.')
        symbol, period = args[0].upper(), args[1]
        name = 'threshold_percent' if len(args) == 3 else args[2]
        parsed = validate(name, args[-1], market=True)
        settings.setdefault('market_rules', {}).setdefault(symbol, {}).setdefault(period, {})[name] = parsed
        if name == 'threshold_percent':
            settings.setdefault('market_thresholds', {}).setdefault(symbol, {})[period] = parsed
    elif command == '/source':
        args = value.split()
        config = config or json.loads(radar.CONFIG_PATH.read_text(encoding='utf-8'))
        feeds = config.get('all_feeds', config['feeds'])
        if len(args) != 2 or not args[0].isdigit() or not 0 <= int(args[0]) < len(feeds) or args[1] not in ('on', 'off'):
            raise ValueError('Оберіть джерело в меню.')
        name = feeds[int(args[0])]['name']
        disabled = set(settings.get('disabled_sources', []))
        disabled.discard(name) if args[1] == 'on' else disabled.add(name)
        settings['disabled_sources'] = sorted(disabled)
    else:
        raise ValueError('Відкрийте /settings і оберіть параметр.')


def handle_update(update, state, config):
    callback = update.get('callback_query')
    message = callback.get('message', {}) if callback else update.get('message', {})
    sender = (callback or message).get('from', {})
    chat = message.get('chat', {})
    user_id = sender.get('id')
    if chat.get('type') != 'private' or chat.get('id') != user_id:
        return
    if not callback and message.get('text', '').strip().split('@')[0] == '/id':
        send_private(user_id, f'Ваш Telegram ID: <code>{user_id}</code>')
        return
    if not is_admin(user_id, config):
        print('Control: ignored non-admin private update')
        return
    from control_ui import handle_admin
    handle_admin(update, state, config)


def main():
    if not os.getenv('TELEGRAM_BOT_TOKEN', '').strip():
        print('Control skipped: Telegram token missing')
        return
    state = radar.load_state()
    config = json.loads(radar.CONFIG_PATH.read_text(encoding='utf-8'))
    hook = telegram('getWebhookInfo', {})
    if hook.get('url'):
        expected = config.get('control_webhook_url', '')
        if hook['url'] != expected:
            raise RuntimeError('Unexpected Telegram webhook; refusing to poll')
        secret = hashlib.sha256((os.environ['TELEGRAM_BOT_TOKEN'] + ':control-webhook-v1').encode()).hexdigest()
        remote = radar.json_request(expected.replace('/webhook', '/settings'),
                                    headers={'Authorization': 'Bearer ' + secret})
        if not isinstance(remote.get('settings'), dict):
            raise RuntimeError('Invalid remote settings')
        state['settings'] = remote['settings']
        radar.save_state(state)
        print('Webhook active; latest admin settings synchronized')
        return
    bot = telegram('getMe', {})
    print(f"Control bot: @{bot.get('username', 'unknown')}")
    offset = int(state.get('telegram_offset', 0))
    updates = telegram('getUpdates', {'offset': offset, 'limit': 100, 'timeout': 0,
                                      'allowed_updates': ['message', 'callback_query']})
    for update in updates:
        try:
            handle_update(update, state, config)
        except Exception as err:
            print(f'Control update failed ({type(err).__name__}: {err})')
            break
        state['telegram_offset'] = max(int(state.get('telegram_offset', 0)),
                                       int(update['update_id']) + 1)
    if state.get('telegram_offset', 0) != offset or 'settings' in state:
        radar.save_state(state)
    print(f'Control checked {len(updates)} updates; admin configured={bool(config.get("admin_user_hashes"))}')


if __name__ == '__main__':
    main()
