"""Data-driven detailed settings pages. Every displayed control has a runtime consumer."""
from html import escape
from settings_schema import OPTIONS, MARKET_OPTIONS, GROUPS
import radar


def describe(field):
    if field.startswith('x_') and field[2:] in OPTIONS:
        return OPTIONS[field[2:]]
    if field.startswith('r_'):
        parts = field.split('_', 3)
        if len(parts) == 4 and parts[1] in ('BTC', 'ETH', 'SOL') and parts[2] in ('1h', '24h'):
            return MARKET_OPTIONS.get(parts[3])
    return None


def value(current, field):
    if field.startswith('x_'):
        return current[field[2:]]
    _, symbol, period, name = field.split('_', 3)
    return current['market_alerts'][symbol][period][name]


def label(value):
    if isinstance(value, bool):
        return '🟢 увімкнено' if value else '⏸ вимкнено'
    return str(value) if value != '' else 'не задано'


def parent(field):
    return 'group_' + describe(field)[5] if field.startswith('x_') else 'rules_' + '_'.join(field.split('_')[1:3])


def command(field, raw):
    if not describe(field):
        raise ValueError('Невідомий параметр.')
    if field.startswith('x_'):
        return '/set ' + field[2:] + ' ' + raw
    _, symbol, period, name = field.split('_', 3)
    return f'/market {symbol} {period} {name} {raw}'


def render(state, config, page):
    from control_ui import button, back
    current = radar.effective_config(config, state)
    if page == 'advanced':
        rows = [[button(title, 'page:group_' + group)] for group, title in GROUPS.items()]
        rows += [[button('🗞 Увімкнути / вимкнути джерела', 'page:sources')], back()]
        return ('<b>⚙️ Розширені налаштування</b>\n\n'
                'Оберіть розділ, потім параметр. На кнопці видно його поточне значення. '
                'Можна вибрати підказаний варіант або ввести будь-яке значення в дозволеному діапазоні.\n\n'
                'Перевірка фактів, захист від повторів і доступ тільки власникам залишаються активними.'), rows
    if page.startswith('group_') and page[6:] in GROUPS:
        group = page[6:]
        rows = []
        for name, spec in OPTIONS.items():
            if spec[5] == group:
                caption = spec[0] + ': ' + label(current[name]).replace('\n', ' ')
                rows.append([button(caption[:60], 'page:x_' + name)])
        if group == 'market':
            rows.append([button('Параметри BTC / ETH / SOL', 'page:market')])
        rows.append(back('advanced'))
        return f'<b>{GROUPS[group]}</b>\n\nНа кожній кнопці — поточний стан. Натисніть параметр для пояснення та зміни.', rows
    if page == 'sources':
        rows = []
        disabled = current.get('disabled_sources', [])
        for index, feed in enumerate(config.get('all_feeds', config['feeds'])):
            enabled = feed['name'] not in disabled
            rows.append([button(('🟢 ' if enabled else '⏸ ') + feed['name'],
                                f'source:{index}:' + ('off' if enabled else 'on'))])
        rows.append(back('advanced'))
        return ('<b>🗞 Джерела новин</b>\n\n🟢 — бот використовує джерело. ⏸ — пропускає. '
                'Натисніть назву, щоб перемкнути. Якщо вимкнути всі джерела, новин не буде.'), rows
    if page.startswith('rules_'):
        parts = page.split('_')
        if len(parts) != 3 or parts[1] not in ('BTC', 'ETH', 'SOL') or parts[2] not in ('1h', '24h'):
            return None
        _, symbol, period = parts
        rows = [[button((spec[0] + ': ' + label(current['market_alerts'][symbol][period][name]))[:60],
                         f'page:r_{symbol}_{period}_{name}')] for name, spec in MARKET_OPTIONS.items()]
        rows.append(back('coin_' + symbol))
        return f'<b>💰 {symbol} · {period} — усі правила</b>\n\nПоріг, повтори, терміновість і перемикач цього алерта налаштовуються окремо.', rows
    spec = describe(page)
    if not spec:
        return None
    title, kind, default, low, high, group, choices, explanation = spec
    actual = value(current, page)
    text = f'<b>{escape(title)}</b>\n\nЗараз: <b>{escape(label(actual))}</b>\n\n{escape(explanation)}'
    if kind in ('int', 'float'):
        text += f'\n\nДозволено: {low}–{high}.'
    rows = []
    if kind == 'bool':
        rows.append([button(('✅ ' if actual else '') + 'Увімкнути', f'set:{page}:true'),
                     button(('✅ ' if not actual else '') + 'Вимкнути', f'set:{page}:false')])
    else:
        buttons = [button(('✅ ' if actual == option else '') + str(option), f'set:{page}:{option}') for option in choices]
        rows += [buttons[i:i+3] for i in range(0, len(buttons), 3)]
        rows.append([button('✏️ Ввести своє', 'ask:' + page)])
        if kind == 'text' and low == 0:
            rows.append([button('Очистити текст', f'set:{page}:')])
    rows.append(back(parent(page)))
    return text, rows


def prompt_text(field):
    spec = describe(field)
    title, kind, default, low, high, group, choices, explanation = spec
    if kind in ('int', 'float'):
        instruction = ('ціле число' if kind == 'int' else 'число') + f' від {low} до {high}'
    elif kind == 'url':
        instruction = 'посилання http:// або https://'
    else:
        instruction = f'текст довжиною до {high} символів'
    return f'<b>✏️ {escape(title)}</b>\n\n{escape(explanation)}\n\nНадішліть наступним повідомленням {instruction}.'
