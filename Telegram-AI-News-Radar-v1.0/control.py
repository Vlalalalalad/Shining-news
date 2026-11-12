#!/usr/bin/env python3
"""Private Telegram control panel, polled by a separate GitHub Actions job."""
from __future__ import annotations

from html import escape
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


def send_private(chat_id, text, keyboard=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
               'link_preview_options': {'is_disabled': True}}
    if keyboard:
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
    current = radar.effective_config(config, state)
    mode = current.get('branding_mode', 'auto')
    market = current['market_alerts']
    text = (
        '<b>Налаштування новин</b>\n'
        f"Новини: {'увімкнено' if current.get('news_enabled', True) else 'вимкнено'}\n"
        f"Реклама: {escape(mode)}, {current.get('branding_percent', 70)}% постів, "
        f"{current.get('branding_ai_percent', 80)}% фраз від Gemini\n"
        f"Свій текст: {escape(str(current.get('branding_text', '') or 'не задано'))}\n"
        f"Ліміт: {current.get('max_regular_per_day', 5)} звичайних на день\n"
        f"Мінімальний інтервал: {current.get('min_post_gap_minutes', 0)} хв\n"
        f"Поріг новин: {current['importance_threshold']}/100\n"
        f"Максимум за запуск: {current['max_posts_per_run']}\n"
        f"BTC/ETH/SOL 1г/24г: " + ', '.join(
            f"{symbol} {market[symbol]['1h']['threshold_percent']:g}%/"
            f"{market[symbol]['24h']['threshold_percent']:g}%"
            for symbol in ('BTC', 'ETH', 'SOL')) + '\n\n'
        '<b>Команди</b>\n'
        '/news on|off · /brand auto|custom|off\n'
        '/brandtext ваш текст із FINDOLLAR\n'
        '/limit 0..10 · /gap 0..240 · /threshold 75..100\n'
        '/perrun 1..5 · /ads 0..100 · /aiads 0..100\n'
        '/market BTC 1h 5 (також ETH, SOL і 24h)\n'
        '/id — показати свій Telegram ID')
    keyboard = [
        [{'text': 'Новини: увімкнути'}, {'text': 'Новини: вимкнути'}],
        [{'text': 'Реклама: авто'}, {'text': 'Реклама: свій текст'},
         {'text': 'Реклама: вимкнути'}],
        [{'text': 'Показати налаштування'}],
    ]
    return text, keyboard


def set_number(settings, name, raw, low, high):
    if not raw.isdecimal():
        raise ValueError(f'Вкажіть ціле число від {low} до {high}.')
    value = int(raw)
    if not low <= value <= high:
        raise ValueError(f'Вкажіть число від {low} до {high}.')
    settings[name] = value


def apply_command(text, settings):
    parts = text.strip().split(maxsplit=1)
    command = parts[0].split('@')[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ''
    if command == '/news' and value in ('on', 'off'):
        settings['news_enabled'] = value == 'on'
    elif command == '/brand' and value in ('auto', 'custom', 'off'):
        if value == 'custom' and not settings.get('branding_text'):
            raise ValueError('Спочатку задайте текст командою /brandtext.')
        settings['branding_mode'] = value
    elif command == '/brandtext':
        if not 5 <= len(value) <= 200 or not radar.russian_copy(value.replace('FINDOLLAR', '')):
            raise ValueError('Текст має бути російською, довжиною 5–200 символів.')
        if re.search(r'https?://|<|>', value, re.I):
            raise ValueError('Надішліть лише текст без URL або HTML.')
        settings['branding_text'] = value
        settings['branding_mode'] = 'custom'
    elif command in ('/limit', '/gap', '/threshold', '/perrun', '/ads', '/aiads'):
        name, low, high = {
            '/limit': ('max_regular_per_day', 0, 10),
            '/gap': ('min_post_gap_minutes', 0, 240),
            '/threshold': ('importance_threshold', 75, 100),
            '/perrun': ('max_posts_per_run', 1, 5),
            '/ads': ('branding_percent', 0, 100),
            '/aiads': ('branding_ai_percent', 0, 100),
        }[command]
        set_number(settings, name, value, low, high)
    elif command == '/market':
        args = value.split()
        if len(args) != 3 or args[0].upper() not in ('BTC', 'ETH', 'SOL') or args[1] not in ('1h', '24h'):
            raise ValueError('Формат: /market BTC 1h 5 (BTC/ETH/SOL, 1h/24h).')
        try:
            threshold = float(args[2])
        except ValueError:
            raise ValueError('Поріг має бути числом від 0.5 до 50%.') from None
        if not 0.5 <= threshold <= 50:
            raise ValueError('Поріг має бути числом від 0.5 до 50%.')
        settings.setdefault('market_thresholds', {}).setdefault(args[0].upper(), {})[args[1]] = threshold
    else:
        raise ValueError('Невідома команда або значення. Надішліть /settings.')


def handle_update(update, state, config):
    callback = update.get('callback_query')
    message = callback.get('message', {}) if callback else update.get('message', {})
    sender = (callback or message).get('from', {})
    chat = message.get('chat', {})
    user_id = sender.get('id')
    raw_text = message.get('text', '')
    command = raw_text.split(maxsplit=1)[0].split('@')[0] if raw_text.startswith('/') else 'text_or_button'
    print(f"Control update: type={chat.get('type', 'unknown')} "
          f"admin={is_admin(user_id, config)} command={command}")
    if chat.get('type') != 'private' or chat.get('id') != user_id:
        return
    if not callback and message.get('text', '').split(maxsplit=1)[0:1] == ['/id']:
        send_private(user_id, f'Ваш Telegram ID: <code>{user_id}</code>')
        return
    if not is_admin(user_id, config):
        print('Control: ignored non-admin private update')
        return
    settings = state.setdefault('settings', {})
    if callback:
        value = callback.get('data', '')
        if value.startswith('news:') or value.startswith('brand:'):
            try:
                apply_command('/' + value.replace(':', ' ', 1), settings)
            except ValueError as err:
                try:
                    telegram('answerCallbackQuery', {'callback_query_id': callback['id'],
                                                     'text': str(err)[:180]})
                except RuntimeError:
                    pass
                return
        elif value != 'settings:show':
            return
        try:
            telegram('answerCallbackQuery', {'callback_query_id': callback['id']})
        except RuntimeError:
            print('Control: callback expired before poll; settings still applied')
    else:
        text = message.get('text', '').strip()
        text = {
            'Новини: увімкнути': '/news on',
            'Новини: вимкнути': '/news off',
            'Реклама: авто': '/brand auto',
            'Реклама: свій текст': '/brand custom',
            'Реклама: вимкнути': '/brand off',
            'Показати налаштування': '/settings',
        }.get(text, text)
        if text not in ('/start', '/settings', '/help'):
            try:
                apply_command(text, settings)
            except (ValueError, IndexError) as err:
                send_private(user_id, escape(str(err)))
                return
    view, keyboard = settings_view(state, config)
    send_private(user_id, view, keyboard)


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
