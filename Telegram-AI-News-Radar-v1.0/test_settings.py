"""Behavior checks for flexible settings all the way into publishing decisions."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar
import control
import control_ui
import settings_schema


class FlexibleSettingsTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(radar.CONFIG_PATH.read_text(encoding='utf-8'))
        self.config['admin_user_hashes'] = [hashlib.sha256(b'100').hexdigest()]
        self.now = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
        self.state = {'settings': {}, 'published': [], 'market_alerts': {}}

    def callback(self, action):
        return {'callback_query': {'id': 'test', 'from': {'id': 100}, 'data': 'ui:' + action,
                'message': {'chat': {'id': 100, 'type': 'private'}}}}

    def test_zero_one_and_large_values_reach_runtime(self):
        settings = self.state['settings']
        for command in ('/threshold 0', '/limit -1', '/perrun 20', '/gap 1000',
                        '/market SOL 24h cooldown_hours 0',
                        '/market SOL 24h threshold_percent 0.1'):
            control.apply_command(command, settings)
        actual = radar.effective_config(self.config, self.state)
        self.assertEqual(actual['importance_threshold'], 0)
        self.assertEqual(actual['max_regular_per_day'], -1)
        self.assertEqual(actual['max_posts_per_run'], 20)
        self.assertEqual(actual['min_post_gap_minutes'], 1000)
        self.assertEqual(actual['market_alerts']['SOL']['24h']['cooldown_hours'], 0)
        self.assertEqual(actual['market_alerts']['SOL']['24h']['threshold_percent'], 0.1)
        for invalid in ('/threshold -1', '/threshold 101', '/market SOL 1h nan',
                        '/set quiet_start_hour 24', '/set TELEGRAM_BOT_TOKEN anything'):
            with self.assertRaises(ValueError):
                control.apply_command(invalid, settings)
        control.apply_command('/threshold 1', settings)
        self.assertEqual(radar.effective_config(self.config, self.state)['importance_threshold'], 1)

    def test_low_scored_posts_count_and_unlimited_is_respected(self):
        article = {'id': 'a', 'source': 'Official', 'domain': 'official.example',
                   'official': True, 'url': 'https://official.example/a', 'added_at': radar.iso(self.now)}
        event = {'score': 1, 'event_key': 'event', 'title_ru': 'Подтвержденное событие в экономике',
                 'body_ru': 'Официальный источник подтвердил это событие.', 'evidence_ids': ['a']}
        state = {'settings': {'importance_threshold': 0, 'max_regular_per_day': 1},
                 'known_ids': {}, 'article_cache': [article], 'ai_pending': False,
                 'published': [{'at': radar.iso(self.now), 'score': 1, 'key': 'previous'}]}
        self.assertEqual(radar.count_regular_today(state, self.now), 1)
        with patch.object(radar, 'scan_feeds', return_value=[article]), \
             patch.object(radar, 'ask_gemini', return_value=[event]), \
             patch.object(radar, 'send_telegram', return_value=True) as send:
            radar.process_news(radar.effective_config(self.config, state), state, self.now, True)
            send.assert_not_called()
            state['settings']['max_regular_per_day'] = -1
            radar.process_news(radar.effective_config(self.config, state), state, self.now, True)
            send.assert_called_once()
        self.assertEqual(radar.count_regular_today(state, self.now), 2)

    def test_custom_quiet_hours_and_urgent_override(self):
        config = {**self.config, 'quiet_start_hour': 9, 'quiet_end_hour': 17,
                  'quiet_allow_urgent': False}
        self.assertTrue(radar.is_quiet_time(self.now, config))
        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test', 'TELEGRAM_CHAT_ID': '@test'}), \
             patch.object(radar, 'json_request', return_value={'ok': True}) as api:
            radar.send_telegram('тест', urgent=True, now=self.now, config=config)
        self.assertTrue(api.call_args.args[1]['disable_notification'])
        self.assertTrue(radar.is_quiet_time(self.now, {**config, 'quiet_start_hour': 4, 'quiet_end_hour': 4}))
        self.assertFalse(radar.is_quiet_time(self.now, {**config, 'quiet_enabled': False}))

    def test_market_switches_and_repeat_parameters_are_live(self):
        self.state['settings'] = {'market_rules': {
            symbol: {period: {'enabled': symbol == 'ETH' and period == '1h',
                              'cooldown_hours': 0, 'renotify_extra_percent': 0, 'threshold_percent': 0}
                     for period in ('1h', '24h')} for symbol in ('BTC', 'ETH', 'SOL')}}
        config = radar.effective_config(self.config, self.state)
        with patch.object(radar, 'market_snapshot', return_value={'1h': (100, 101, 1), '24h': (100, 102, 2)}) as fetch, \
             patch.object(radar, 'send_telegram', return_value=True) as send:
            radar.process_market(config, self.state, self.now, True)
            radar.process_market(config, self.state, self.now, True)
            self.assertEqual(send.call_count, 2)
            self.assertTrue(all(call.args[0] == 'ETH' for call in fetch.call_args_list))
            config['market_enabled'] = False
            fetch.reset_mock()
            radar.process_market(config, self.state, self.now, True)
            fetch.assert_not_called()

    def test_advanced_menu_guides_input_and_source_selection(self):
        with patch.object(control, 'telegram'), patch.object(control, 'send_private') as send:
            control.handle_update(self.callback('ask:x_importance_threshold'), self.state, self.config)
            control.handle_update({'message': {'from': {'id': 100}, 'chat': {'id': 100, 'type': 'private'}, 'text': '0'}},
                                  self.state, self.config)
            self.assertEqual(self.state['settings']['importance_threshold'], 0)
            self.assertIn('Зараз: <b>0</b>', send.call_args.args[1])
            control.handle_update(self.callback('set:r_SOL_24h_cooldown_hours:0'), self.state, self.config)
            self.assertEqual(self.state['settings']['market_rules']['SOL']['24h']['cooldown_hours'], 0)
            control.handle_update(self.callback('source:0:off'), self.state, self.config)
            actual = radar.effective_config(self.config, self.state)
            self.assertNotIn(self.config['feeds'][0], actual['feeds'])
            self.assertEqual(len(self.config['feeds']), len(actual['feeds']) + 1)

    def test_brand_and_text_preferences_preserve_telegram_limits(self):
        config = radar.effective_config(self.config, {'settings': {
            'brand_name': 'My & App', 'brand_url': 'https://example.com/app',
            'branding_quote': False, 'branding_skip_score': 101,
            'max_title_chars': 300, 'max_body_chars': 2500, 'max_source_links': 0}})
        event = {'event_key': 'x', 'title_ru': 'Рынок растет', 'body_ru': 'Подтвержденная новость.',
                 'brand_line_ru': 'Следи за своими финансами в FINDOLLAR.'}
        line = radar.brand_line(event, [], config, 100)
        self.assertNotIn('<blockquote>', line)
        self.assertIn('>My &amp; App</a>', line)
        long = {**event, 'title_ru': 'З' * 300, 'body_ru': 'Н' * 2500}
        message = radar.post_text(long, [], '<blockquote>' + '💚' * 800 + '</blockquote>', config)
        visible = radar.unescape(radar.re.sub(r'<[^>]*>', '', message))
        self.assertLessEqual(len(visible.encode('utf-16-le')) // 2, 4096)
        self.assertNotIn('Источники:', message)

    def test_advanced_screens_fit_telegram_message_and_button_limits(self):
        from settings_schema import OPTIONS, MARKET_OPTIONS, GROUPS
        pages = ['advanced', 'sources'] + ['group_' + key for key in GROUPS]
        pages += ['x_' + key for key in OPTIONS]
        pages += [f'r_{symbol}_{period}_{key}' for symbol in ('BTC', 'ETH', 'SOL')
                  for period in ('1h', '24h') for key in MARKET_OPTIONS]
        for page in pages:
            message, rows = control_ui.view(self.state, self.config, page)
            visible = radar.unescape(radar.re.sub(r'<[^>]*>', '', message))
            self.assertLessEqual(len(visible.encode('utf-16-le')) // 2, 4096, page)
            for row in rows:
                for button in row:
                    self.assertLessEqual(len(button['callback_data'].encode('utf-8')), 64, page)


if __name__ == '__main__':
    unittest.main()
