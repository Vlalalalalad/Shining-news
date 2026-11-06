"""Offline checks for market windows, delivery rules and state safety."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(radar.CONFIG_PATH.read_text(encoding='utf-8'))
        self.now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

    def test_market_windows_use_rolling_24h_and_trade_1h(self):
        close = int(self.now.timestamp() * 1000)
        target = close - 3_600_000

        def fake_api(url, *args, **kwargs):
            if '/ticker/24hr?' in url:
                return {'lastPrice': '95', 'openPrice': '100', 'closeTime': close}
            if '/aggTrades?' in url:
                return [{'p': '100', 'T': target + 20}]
            raise AssertionError(url)

        with patch.object(radar, 'json_request', side_effect=fake_api):
            snap = radar.market_snapshot('BTC', self.now)
        self.assertAlmostEqual(snap['1h'][2], -5)
        self.assertAlmostEqual(snap['24h'][2], -5)

    def test_market_alerts_dedupe_separately_by_symbol_and_period(self):
        state = {'market_alerts': {}}
        snap = {'1h': (100, 94, -6), '24h': (100, 94, -6)}
        with patch.object(radar, 'market_snapshot', return_value=snap), \
             patch.object(radar, 'send_telegram', return_value=True) as send:
            radar.process_market(self.config, state, self.now, True)
            self.assertEqual(send.call_count, 6)
            self.assertIn('<a href="https://www.binance.com/en/trade/BTC_USDT">Binance Spot</a>',
                          send.call_args_list[0].args[0])
            radar.process_market(self.config, state, self.now, True)
            self.assertEqual(send.call_count, 6)
        self.assertEqual(len(state['market_alerts']), 6)

    def test_night_silent_except_emergency_and_kyiv_day(self):
        night = datetime(2026, 11, 5, 22, 30, tzinfo=timezone.utc)
        sent = []

        def fake_api(url, payload=None, headers=None):
            sent.append(payload)
            return {'ok': True}

        with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test',
                                       'TELEGRAM_CHAT_ID': '@test'}), \
             patch.object(radar, 'json_request', side_effect=fake_api):
            radar.send_telegram('тест', now=night)
            radar.send_telegram('тест', urgent=True, now=night)
        self.assertTrue(sent[0]['disable_notification'])
        self.assertFalse(sent[1]['disable_notification'])
        self.assertEqual(sent[0]['parse_mode'], 'HTML')
        self.assertEqual(sent[0]['link_preview_options'], {'is_disabled': True})
        self.assertEqual(radar.count_regular_today(
            {'published': [{'at': '2026-11-05T22:10:00+00:00', 'score': 80}]},
            night), 1)

    def test_dry_run_never_sends_or_writes_state(self):
        snap = {'1h': (100, 94, -6), '24h': (100, 94, -6)}
        state = {'market_alerts': {}}
        with patch.object(radar, 'market_snapshot', return_value=snap), \
             patch.object(radar, 'send_telegram') as send:
            radar.process_market(self.config, state, self.now, False)
        send.assert_not_called()
        self.assertFalse(any(a.get('active') for a in state['market_alerts'].values()))

    def test_news_sources_are_clickable_names_without_raw_links(self):
        event = {'title_ru': 'Рынок <растет> & меняется',
                 'body_ru': 'Компания A & B объявила о сделке.'}
        sources = [
            {'domain': 'one.example', 'source': 'Первое & издание',
             'url': 'https://one.example/story?x=1&y=2'},
            {'domain': 'two.example', 'source': 'Второе издание',
             'url': 'https://two.example/story'},
        ]
        rendered = radar.post_text(event, sources)
        self.assertIn('Рынок &lt;растет&gt; &amp; меняется', rendered)
        self.assertIn('Компания A &amp; B', rendered)
        self.assertIn('Источники:\n<a href="https://one.example/story?x=1&amp;y=2">'
                      'Первое &amp; издание</a>, '
                      '<a href="https://two.example/story">Второе издание</a>', rendered)
        self.assertNotIn('Первое & издание: https://', rendered)

    def test_news_requires_independent_sources_and_limits_regular_posts(self):
        articles = [
            {'id': 'a', 'source': 'CoinDesk', 'domain': 'coindesk.com',
             'official': False, 'url': 'https://coindesk.com/a',
             'added_at': radar.iso(self.now)},
            {'id': 'b', 'source': 'Decrypt', 'domain': 'decrypt.co',
             'official': False, 'url': 'https://decrypt.co/b',
             'added_at': radar.iso(self.now)},
        ]
        event = {'score': 85, 'event_key': 'market-event',
                 'title_ru': 'Крупное событие на финансовом рынке',
                 'body_ru': 'Два независимых издания подтвердили важное событие.',
                 'evidence_ids': ['a']}
        state = {'known_ids': {}, 'article_cache': articles,
                 'published': [], 'ai_pending': False}
        with patch.object(radar, 'scan_feeds', return_value=articles), \
             patch.object(radar, 'ask_gemini', return_value=[event]), \
             patch.object(radar, 'send_telegram', return_value=True) as send:
            radar.process_news(self.config, state, self.now, True)
            send.assert_not_called()
            event['evidence_ids'] = ['a', 'b']
            radar.process_news(self.config, state, self.now, True)
            send.assert_called_once()
            self.assertEqual(len(state['published']), 1)
            state['published'].extend([{'at': radar.iso(self.now), 'score': 80,
                                        'key': f'old-{i}'} for i in range(4)])
            event['event_key'] = 'another-event'
            event['title_ru'] = 'Другое крупное событие на рынке'
            radar.process_news(self.config, state, self.now, True)
            send.assert_called_once()

    def test_ai_article_selection_balances_publishers(self):
        articles = []
        for source in ('CoinDesk', 'BBC', 'NASA'):
            for i in range(12):
                articles.append({'id': f'{source}-{i}', 'title': 'Title',
                                 'summary': 'Summary', 'source': source,
                                 'domain': f'{source.lower()}.example',
                                 'official': source == 'NASA',
                                 'category': 'Science', 'url': 'https://example.com'})
        config = {**self.config, 'max_ai_articles': 9}
        prompts = []

        def fake_api(url, payload=None, headers=None):
            prompts.append(payload['contents'][0]['parts'][0]['text'])
            return {'candidates': [{'content': {'parts': [{'text': '{"events":[]}'}]}}]}

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test'}), \
             patch.object(radar, 'json_request', side_effect=fake_api):
            radar.ask_gemini(articles, config)
        records = json.loads(prompts[0].split('RSS records:\n', 1)[1])
        self.assertEqual({s: sum(r['source'] == s for r in records)
                          for s in ('CoinDesk', 'BBC', 'NASA')},
                         {'CoinDesk': 3, 'BBC': 3, 'NASA': 3})

    def test_main_respects_live_and_dry_run_switches(self):
        state = {'market_alerts': {}, 'published': []}
        with patch.object(radar, 'load_state', return_value=state), \
             patch.object(radar, 'process_market') as market, \
             patch.object(radar, 'process_news') as news, \
             patch.object(radar, 'save_state') as save:
            with patch.dict('os.environ', {'PUBLISH_ENABLED': 'true', 'DRY_RUN': 'true'}):
                radar.main()
            self.assertFalse(market.call_args.args[3])
            self.assertFalse(news.call_args.args[3])
            save.assert_not_called()
            with patch.dict('os.environ', {'PUBLISH_ENABLED': 'true', 'DRY_RUN': 'false'}):
                radar.main()
            self.assertTrue(market.call_args.args[3])
            self.assertTrue(news.call_args.args[3])
            save.assert_called_once()


if __name__ == '__main__':
    unittest.main()
