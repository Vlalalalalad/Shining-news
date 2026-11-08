"""Offline checks for admin-only controls and deterministic branding."""
import json
import hashlib
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import control
import radar


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(radar.CONFIG_PATH.read_text(encoding='utf-8'))
        self.config['admin_user_hashes'] = [hashlib.sha256(b'100').hexdigest()]
        self.state = {'settings': {}, 'published': [], 'market_alerts': {}}

    def message(self, sender, text):
        return {'update_id': 42, 'message': {
            'from': {'id': sender}, 'chat': {'id': sender, 'type': 'private'},
            'text': text}}

    def test_admin_commands_reject_strangers_and_groups(self):
        sent = []
        with patch.object(control, 'send_private', side_effect=lambda *a, **k: sent.append(a)):
            control.handle_update(self.message(200, '/limit 10'), self.state, self.config)
            group = self.message(100, '/limit 10')
            group['message']['chat'] = {'id': -10, 'type': 'group'}
            control.handle_update(group, self.state, self.config)
            self.assertEqual(self.state['settings'], {})
            self.assertEqual(sent, [])
            control.handle_update(self.message(200, '/id'), self.state, self.config)
            self.assertIn('200', sent[0][1])
            control.handle_update(self.message(100, '/limit 7'), self.state, self.config)
            self.assertEqual(self.state['settings']['max_regular_per_day'], 7)
            self.assertEqual(len(sent), 2)

    def test_settings_are_bounded_and_market_windows_separate(self):
        settings = self.state['settings']
        control.apply_command('/brandtext 💚 Твои финансы под контролем. FINDOLLAR', settings)
        control.apply_command('/market ETH 1h 6.5', settings)
        control.apply_command('/news off', settings)
        with self.assertRaises(ValueError):
            control.apply_command('/threshold 10', settings)
        merged = radar.effective_config(self.config, self.state)
        self.assertFalse(merged['news_enabled'])
        self.assertEqual(merged['market_alerts']['ETH']['1h']['threshold_percent'], 6.5)
        self.assertEqual(merged['market_alerts']['ETH']['24h']['threshold_percent'], 5)
        self.assertEqual(self.config['market_alerts']['ETH']['1h']['threshold_percent'], 5)

    def test_private_buttons_apply_idempotent_choices(self):
        callback = {'callback_query': {'id': 'button-1', 'data': 'news:off',
                    'from': {'id': 100},
                    'message': {'chat': {'id': 100, 'type': 'private'}}}}
        with patch.object(control, 'telegram') as api, patch.object(control, 'send_private'):
            control.handle_update(callback, self.state, self.config)
            control.handle_update(callback, self.state, self.config)
        self.assertFalse(self.state['settings']['news_enabled'])
        self.assertEqual(api.call_count, 2)
        self.assertTrue(all(call.args[0] == 'answerCallbackQuery' for call in api.call_args_list))

    def test_branding_is_stable_and_excludes_sensitive_news(self):
        sources = [{'title': 'Markets', 'source': 'News', 'domain': 'news.example',
                    'url': 'https://news.example/a'}]
        event = {'event_key': 'abc', 'title_ru': 'Рынок изменился',
                 'body_ru': 'Компания объявила о сделке.',
                 'brand_line_ru': '💚 Следи за своими финансами вместе с FINDOLLAR.'}
        settings = {**self.config, 'branding_percent': 100, 'branding_ai_percent': 100}
        line = radar.brand_line(event, sources, settings, 85)
        self.assertIn('<a href="https://t.me/findollarapp">FINDOLLAR</a>', line)
        self.assertEqual(line, radar.brand_line(event, sources, settings, 85))
        self.assertEqual(radar.brand_line(event, sources, settings, 90), '')
        event['title_ru'] = 'При землетрясении погибли люди'
        self.assertEqual(radar.brand_line(event, sources, settings, 85), '')
        event['title_ru'] = 'Рынок изменился'
        settings['branding_mode'] = 'custom'
        settings['branding_text'] = '💚 Мои финансы. FINDOLLAR'
        self.assertIn('Мои финансы.', radar.brand_line(event, sources, settings, 85))
        settings['branding_percent'] = 0
        self.assertEqual(radar.brand_line(event, sources, settings, 85), '')

    def test_polling_saves_offset_and_settings_only_for_admin(self):
        updates = [self.message(200, '/limit 10'), self.message(100, '/limit 7')]
        updates[1]['update_id'] = 43
        saved = []
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test'}), \
             patch.object(control.json, 'loads', side_effect=lambda value: self.config), \
             patch.object(radar, 'load_state', return_value=self.state), \
             patch.object(control, 'telegram', return_value=updates) as api, \
             patch.object(control, 'send_private'), \
             patch.object(radar, 'save_state', side_effect=lambda state: saved.append(dict(state))):
            control.main()
        self.assertEqual(api.call_args.args[0], 'getUpdates')
        self.assertEqual(self.state['telegram_offset'], 44)
        self.assertEqual(saved[0]['settings']['max_regular_per_day'], 7)


if __name__ == '__main__':
    unittest.main()
