"""Plain-language Telegram settings screens and per-admin guided input."""
from datetime import timedelta
from html import escape, unescape
import re
import radar

FIELDS = {
    'limit': ('max_regular_per_day', 'Новин на день', '/limit', 'limit', [0, 1, 3, 5, 7, 10], 'ціле число від 0 до 10'),
    'gap': ('min_post_gap_minutes', 'Пауза між новинами', '/gap', 'gap', [0, 30, 60, 120, 240], 'кількість хвилин від 0 до 240'),
    'threshold': ('importance_threshold', 'Важливість новин', '/threshold', 'threshold', [75, 80, 85, 90, 95], 'ціле число від 75 до 100'),
    'perrun': ('max_posts_per_run', 'Постів за одну перевірку', '/perrun', 'perrun', [1, 2, 3, 5], 'ціле число від 1 до 5'),
    'ads': ('branding_percent', 'Частка новин із рекламою', '/ads', 'ads', [0, 30, 50, 70, 100], 'відсоток від 0 до 100'),
    'aiads': ('branding_ai_percent', 'Частка фраз від AI', '/aiads', 'aiads', [0, 50, 80, 100], 'відсоток від 0 до 100'),
}
MODES = {'auto': 'Автоматичний підпис', 'custom': 'Мій текст', 'off': 'Вимкнена'}
NAV = {'home', 'news', 'brand', 'market', 'help', *FIELDS}
NOTE = '\n\nЗміни зберігаються одразу. Нові параметри публікацій діють із наступної перевірки радара.'


def button(label, action):
    return {'text': label, 'callback_data': 'ui:' + action}


def back(page='home'):
    return [button('‹ Назад', 'page:' + page), button('🏠 Головне меню', 'page:home')]


def field_value(current, field):
    if field.startswith('m_'):
        _, symbol, period = field.split('_')
        return current['market_alerts'][symbol][period]['threshold_percent']
    return current.get(FIELDS[field][0], {'limit': 5, 'gap': 0, 'ads': 70, 'aiads': 80}.get(field, 3))


def value_label(field, value):
    if field == 'gap':
        return 'Без паузи' if value == 0 else f'{value:g} хв'
    if field in ('ads', 'aiads') or field.startswith('m_'):
        return f'{value:g}%'
    if field == 'threshold':
        return f'{value:g}/100'
    return str(value)


def valid_market_field(field):
    return bool(re.fullmatch(r'm_(BTC|ETH|SOL)_(1h|24h)', field))


def view(state, config, page='home'):
    current = radar.effective_config(config, state)
    enabled = current.get('news_enabled', True)
    mode = current.get('branding_mode', 'auto')
    if page == 'home':
        text = (
            '<b>⚙️ Керування FINDOLLAR</b>\n\n'
            f"📰 Новини: <b>{'🟢 увімкнені' if enabled else '⏸ призупинені'}</b>\n"
            f"До <b>{current.get('max_regular_per_day', 5)}</b> звичайних новин на день; "
            f"пауза — <b>{value_label('gap', current.get('min_post_gap_minutes', 0))}</b>.\n"
            f"💚 Реклама: <b>{MODES.get(mode, 'Автоматичний підпис')}</b>\n"
            f"У {current.get('branding_percent', 70)}% звичайних новин; "
            f"у цінових алертах — {'немає' if mode == 'off' else 'є'}.\n"
            '💰 Цінові алерти BTC, ETH, SOL: <b>увімкнені</b>\n\n'
            'Оберіть розділ нижче. У ньому видно поточне значення й доступні варіанти.' + NOTE)
        rows = [[button('📰 Новини', 'page:news'), button('💚 Рекламний підпис', 'page:brand')],
                [button('💰 Цінові алерти', 'page:market')],
                [button('ℹ️ Як це працює', 'page:help'), button('🔄 Оновити стан', 'page:home')]]
    elif page == 'news':
        text = (
            '<b>📰 Новини</b>\n\n'
            f"Стан: <b>{'🟢 увімкнені' if enabled else '⏸ призупинені'}</b>\n"
            f"Ліміт: <b>{current.get('max_regular_per_day', 5)} на київську добу</b>\n"
            f"Пауза між звичайними постами: <b>{value_label('gap', current.get('min_post_gap_minutes', 0))}</b>\n"
            f"Мінімальна важливість: <b>{current['importance_threshold']}/100</b>\n"
            f"За одну перевірку: до <b>{current['max_posts_per_run']}</b> постів\n\n"
            'Новини 90+ можуть виходити понад денний ліміт і без звичайної паузи. '
            'Призупинення новин не вимикає цінові алерти.' + NOTE)
        rows = [[button('⏸ Призупинити новини' if enabled else '▶️ Увімкнути новини',
                        'news:off' if enabled else 'news:on')],
                [button('Кількість на день', 'page:limit'), button('Пауза між постами', 'page:gap')],
                [button('Важливість новин', 'page:threshold'), button('Постів за перевірку', 'page:perrun')],
                back()]
    elif page == 'brand':
        custom = current.get('branding_text', '') or 'Ще не задано'
        text = (
            '<b>💚 Рекламний підпис</b>\n\n'
            f"Режим: <b>{MODES.get(mode, 'Автоматичний підпис')}</b>\n"
            f"Частка звичайних новин: <b>{current.get('branding_percent', 70)}%</b>\n"
            f"Фрази від AI в автоматичному режимі: <b>{current.get('branding_ai_percent', 80)}%</b>\n"
            f"Мій текст: <i>{escape(custom)}</i>\n\n"
            'Автоматично: фраза під тему новини або перевірений шаблон. '
            'Мій текст: одна ваша фраза.\n'
            'Під новинами 90+ та подіями, визначеними як трагедії чи надзвичайні, реклами немає. '
            'У цінових алертах підпис є, поки рекламу не вимкнено.' + NOTE)
        rows = [[button(('✅ ' if mode == 'auto' else '') + 'Автоматично', 'mode:auto'),
                 button(('✅ ' if mode == 'off' else '') + 'Вимкнути', 'mode:off')],
                [button(('✅ ' if mode == 'custom' else '') + 'Мій текст', 'mode:custom'),
                 button('✏️ Змінити мій текст', 'ask:brandtext')],
                [button('Частка постів із рекламою', 'page:ads')],
                [button('Частка фраз від AI', 'page:aiads'), button('👁 Приклад підпису', 'preview')],
                back()]
    elif page == 'market':
        text = '<b>💰 Цінові алерти</b>\n\n'
        for symbol in ('BTC', 'ETH', 'SOL'):
            windows = current['market_alerts'][symbol]
            text += f"<b>{symbol}</b>: ±{windows['1h']['threshold_percent']:g}% за 1 год · ±{windows['24h']['threshold_percent']:g}% за 24 години\n"
        text += ('\nЦе два окремі пороги. Алерт може прийти як про зростання, так і про падіння. '
                 'Повтори одного руху обмежуються cooldown. Оберіть монету.' + NOTE)
        rows = [[button(symbol, 'page:coin_' + symbol) for symbol in ('BTC', 'ETH', 'SOL')], back()]
    elif page.startswith('coin_') and page[5:] in ('BTC', 'ETH', 'SOL'):
        symbol = page[5:]
        windows = current['market_alerts'][symbol]
        text = (f'<b>💰 {symbol} — пороги алертів</b>\n\n'
                f"За 1 годину: <b>±{windows['1h']['threshold_percent']:g}%</b>\n"
                f"За 24 години: <b>±{windows['24h']['threshold_percent']:g}%</b>\n\n"
                'Нижчий поріг — більше сповіщень. Вищий — тільки сильніші рухи.')
        rows = [[button('Поріг за 1 годину', f'page:m_{symbol}_1h')],
                [button('Поріг за 24 години', f'page:m_{symbol}_24h')], back('market')]
    elif page in FIELDS or valid_market_field(page):
        market = valid_market_field(page)
        value = field_value(current, page)
        title = (f"{page.split('_')[1]}: зміна за {'1 годину' if page.endswith('1h') else '24 години'}"
                 if market else FIELDS[page][1])
        hints = {
            'limit': 'Звичайні новини за київську добу. 0 — не публікувати звичайні; новини 90+ дозволені.',
            'gap': 'Мінімальна пауза між звичайними новинами. Це не точний розклад: перевірка радара може затриматися.',
            'threshold': '75 — більше новин. 90 — лише особливо важливі. Нижче 75 встановити не можна.',
            'perrun': 'Скільки постів максимум може вийти після однієї перевірки.',
            'ads': '70% — приблизно 7 із 10 звичайних новин. 0% прибирає рекламу з новин; для всіх постів вимкніть її в розділі реклами.',
            'aiads': '80% — AI пропонує більшість фраз; решта — готові шаблони. Невдалі фрази теж замінюються шаблоном.',
        }
        text = f'<b>{escape(title)}</b>\n\nЗараз: <b>{value_label(page, value)}</b>\n\n'
        text += 'Поріг однаковий для зростання та падіння.' if market else hints[page]
        text += '\n\nНатисніть нове значення або введіть своє.'
        options = [3, 5, 7, 10] if market else FIELDS[page][4]
        buttons = [button(('✅ ' if value == option else '') + value_label(page, option),
                          f'set:{page}:{option}') for option in options]
        rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
        parent = 'coin_' + page.split('_')[1] if market else ('brand' if page in ('ads', 'aiads') else 'news')
        rows += [[button('✏️ Своє значення', 'ask:' + page)], back(parent)]
    elif page == 'help':
        text = (
            '<b>ℹ️ Як користуватися</b>\n\n'
            '1. Відкрийте розділ.\n2. Подивіться значення біля «Зараз».\n'
            '3. Натисніть варіант — бот підтвердить зміну й покаже новий стан.\n\n'
            'Для власного числа чи рекламного тексту бот попросить наступне повідомлення. '
            'Його можна скасувати кнопкою.\n\n'
            'Команди в Telegram обробляються одразу. Параметри публікацій радар зчитує перед наступною перевіркою. '
            'Автоматична перевірка новин може затримуватися.\n'
            'Нічний режим: 23:00–08:00 Київ, без звуку, крім екстрених подій.\n\n'
            'Повернутися сюди можна командою /settings або /menu.')
        rows = [back()]
    else:
        return view(state, config, 'home')
    return text, rows


def present(user_id, state, config, page, callback=None, notice=''):
    import control
    text, rows = view(state, config, page)
    if notice:
        text = escape(notice) + '\n\n' + text
    if callback and callback.get('message', {}).get('message_id'):
        message = callback['message']
        visible = unescape(re.sub(r'<[^>]*>', '', text))
        if (message.get('text') == visible and
                message.get('reply_markup', {}).get('inline_keyboard') == rows):
            return
        try:
            control.telegram('editMessageText', {
                'chat_id': user_id, 'message_id': callback['message']['message_id'],
                'text': text, 'parse_mode': 'HTML',
                'link_preview_options': {'is_disabled': True},
                'reply_markup': {'inline_keyboard': rows}})
            return
        except RuntimeError as err:
            if 'not modified' in str(err):
                return
    control.send_private(user_id, text, rows, inline=True)


def field_command(field, value):
    if field == 'brandtext':
        return '/brandtext ' + value
    if valid_market_field(field):
        _, symbol, period = field.split('_')
        return f'/market {symbol} {period} {value.replace(",", ".")}'
    if field in FIELDS:
        return FIELDS[field][2] + ' ' + value
    raise ValueError('Невідомий параметр. Відкрийте головне меню.')


def prompt(user_id, session, field):
    import control
    if field not in FIELDS and not valid_market_field(field) and field != 'brandtext':
        raise ValueError('Невідомий параметр.')
    session['pending'] = {'field': field, 'at': radar.iso(radar.utcnow())}
    if field == 'brandtext':
        text = ('<b>✏️ Ваш рекламний підпис</b>\n\nНадішліть наступним повідомленням текст російською '
                '(5–200 символів). Слово FINDOLLAR стане посиланням. Якщо його немає, бот додасть його в кінці.\n\n'
                'Наприклад: Рынок меняется. Следи за своими финансами вместе с FINDOLLAR.\n\n'
                'Після збереження ввімкнеться режим «Мій текст».')
    else:
        allowed = 'число від 0.5 до 50 (відсотки)' if valid_market_field(field) else FIELDS[field][5]
        text = f'<b>✏️ Своє значення</b>\n\nНадішліть наступним повідомленням {allowed}.'
    control.send_private(user_id, text, [[button('Скасувати', 'cancel')]], inline=True)


def handle_admin(update, state, config):
    import control
    callback = update.get('callback_query')
    message = callback.get('message', {}) if callback else update.get('message', {})
    user_id = (callback or message)['from']['id']
    session = state.setdefault('control_ui', {}).setdefault(str(user_id), {})
    settings = state.setdefault('settings', {})
    raw = message.get('text', '').strip()
    if callback:
        try:
            control.telegram('answerCallbackQuery', {'callback_query_id': callback['id']})
        except RuntimeError:
            pass
        data = callback.get('data', '')
        if data.startswith('ui:'):
            action = data[3:].split(':')
            try:
                if action[0] == 'page' and len(action) == 2:
                    session.pop('pending', None)
                    present(user_id, state, config, action[1], callback)
                elif action[0] == 'news' and len(action) == 2:
                    session.pop('pending', None)
                    control.apply_command('/news ' + action[1], settings)
                    present(user_id, state, config, 'news', callback, '✅ Збережено')
                elif action[0] == 'mode' and len(action) == 2:
                    session.pop('pending', None)
                    if action[1] == 'custom' and not settings.get('branding_text'):
                        prompt(user_id, session, 'brandtext')
                    else:
                        control.apply_command('/brand ' + action[1], settings)
                        present(user_id, state, config, 'brand', callback, '✅ Режим збережено')
                elif action[0] == 'set' and len(action) == 3:
                    control.apply_command(field_command(action[1], action[2]), settings)
                    session.pop('pending', None)
                    present(user_id, state, config, action[1], callback, '✅ Нове значення збережено')
                elif action[0] == 'ask' and len(action) == 2:
                    prompt(user_id, session, action[1])
                elif action[0] == 'cancel':
                    session.pop('pending', None)
                    present(user_id, state, config, 'home', callback, 'Введення скасовано')
                elif action[0] == 'preview':
                    current = radar.effective_config(config, state)
                    if current.get('branding_mode') == 'off':
                        notice = 'Реклама вимкнена — підпис не додається.'
                    else:
                        sample = radar.brand_line({'event_key': 'preview', 'title_ru': 'Рынок',
                            'body_ru': '', 'brand_line_ru': ''}, [], {**current, 'branding_percent': 100}, 85)
                        control.send_private(user_id, '<b>Приклад підпису</b>\n\n' + sample +
                            '\n\nВ автоматичному режимі фраза може змінюватися під новину.',
                            [[button('‹ До реклами', 'page:brand')]], inline=True)
                        return
                    present(user_id, state, config, 'brand', callback, notice)
                else:
                    present(user_id, state, config, 'home', callback)
            except (ValueError, IndexError) as err:
                control.send_private(user_id, '⚠️ ' + escape(str(err)),
                                     [[button('🏠 Головне меню', 'page:home')]], inline=True)
            return
        # Compatibility with buttons in old messages.
        if data.startswith(('news:', 'brand:')):
            try:
                control.apply_command('/' + data.replace(':', ' ', 1), settings)
            except ValueError as err:
                control.send_private(user_id, escape(str(err)))
        present(user_id, state, config, 'home', callback)
        return
    command = raw.split(maxsplit=1)[0].split('@')[0].lower() if raw else ''
    if command in ('/start', '/settings', '/menu', '/help', '/cancel') or raw == 'Показати налаштування':
        session.pop('pending', None)
        if not session.get('keyboard_removed'):
            try:
                control.telegram('setMyCommands', {'scope': {'type': 'chat', 'chat_id': user_id},
                    'commands': [{'command': 'settings', 'description': 'Відкрити меню та поточний стан'},
                                 {'command': 'help', 'description': 'Як користуватися налаштуваннями'},
                                 {'command': 'cancel', 'description': 'Скасувати введення'}]})
                control.telegram('setChatMenuButton', {'chat_id': user_id, 'menu_button': {'type': 'commands'}})
            except RuntimeError:
                print('Control: Telegram command menu unavailable')
            control.send_private(user_id, 'Нове меню — на кнопках під повідомленням.', remove_keyboard=True)
            session['keyboard_removed'] = True
        present(user_id, state, config, 'help' if command == '/help' else 'home')
        return
    pending = session.get('pending')
    if pending and not raw.startswith('/'):
        at = radar.parse_date(pending.get('at'))
        if not at or radar.utcnow() - at > timedelta(minutes=15):
            session.pop('pending', None)
            present(user_id, state, config, 'home', notice='Час введення минув. Оберіть параметр знову.')
            return
        try:
            control.apply_command(field_command(pending['field'], raw), settings)
        except ValueError as err:
            control.send_private(user_id, '⚠️ ' + escape(str(err)) + '\nНадішліть виправлене значення або скасуйте.',
                                 [[button('Скасувати', 'cancel')]], inline=True)
            return
        field = pending['field']
        session.pop('pending', None)
        present(user_id, state, config, 'brand' if field == 'brandtext' else field,
                notice='✅ Збережено')
        return
    legacy = {'Новини: увімкнути': '/news on', 'Новини: вимкнути': '/news off',
              'Реклама: авто': '/brand auto', 'Реклама: свій текст': '/brand custom',
              'Реклама: вимкнути': '/brand off'}
    try:
        control.apply_command(legacy.get(raw, raw), settings)
        present(user_id, state, config, 'home', notice='✅ Налаштування збережено')
    except (ValueError, IndexError):
        present(user_id, state, config, 'home',
                notice='Оберіть дію кнопкою нижче. Для власного значення спочатку натисніть «Своє значення».')
