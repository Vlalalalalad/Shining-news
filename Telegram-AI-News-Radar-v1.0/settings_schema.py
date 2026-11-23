"""Shared editable settings: menu, command validation and radar use one schema."""
import math
from urllib.parse import urlparse

# label, kind, default, minimum, maximum, group, suggested values, explanation
OPTIONS = {
    'news_enabled': ('Новини', 'bool', True, None, None, 'news', [], 'Усі новини можна призупинити окремо від цінових алертів.'),
    'importance_threshold': ('Мінімальна важливість', 'int', 75, 0, 100, 'news', [0, 1, 25, 50, 75, 90, 100], 'Повний діапазон 0–100. 0 пропускає будь-яку оцінку, але перевірка джерел залишається.'),
    'max_regular_per_day': ('Звичайних новин на день', 'int', 5, -1, 100000, 'news', [-1, 0, 1, 5, 10, 50], '-1 — без денного ліміту; 0 — жодної звичайної новини. Доба за Києвом.'),
    'max_posts_per_run': ('Постів за одну перевірку', 'int', 3, 0, 100, 'news', [0, 1, 3, 5, 10, 25], '0 — пропускати новинні публікації. До 100 за запуск — технічна межа одного завдання.'),
    'min_post_gap_minutes': ('Пауза між постами, хв', 'int', 0, 0, 1000000, 'news', [0, 1, 15, 30, 60, 240], 'Мінімальна пауза. 0 — без паузи. Це не частота запуску: планувальник може затримувати перевірки.'),
    'priority_score': ('Позалімітні новини від оцінки', 'int', 90, 0, 101, 'news', [0, 75, 90, 95, 100, 101], 'Новини з цієї оцінки не рахуються в денний ліміт і паузу. 101 — усі новини під лімітом; 0 — усі поза лімітом.'),
    'news_emergency_score': ('Термінові новини від оцінки', 'int', 98, 0, 101, 'quiet', [0, 90, 98, 100, 101], 'Терміновим можна дозволити звук уночі. 101 — жодна новина не термінова.'),
    'quiet_enabled': ('Беззвучний нічний режим', 'bool', True, None, None, 'quiet', [], 'У вимкненому стані всі пости надсилаються зі звуком.'),
    'quiet_start_hour': ('Початок тиші, година Києва', 'int', 23, 0, 23, 'quiet', [0, 20, 22, 23], 'Година 0–23. Однаковий початок і кінець означає тишу всю добу.'),
    'quiet_end_hour': ('Кінець тиші, година Києва', 'int', 8, 0, 23, 'quiet', [0, 6, 8, 10], 'Година 0–23 за Києвом.'),
    'quiet_allow_urgent': ('Звук терміновим під час тиші', 'bool', True, None, None, 'quiet', [], 'Вимкніть, щоб навіть термінові новини й сильні рухи ринку були беззвучними в цей період.'),
    'branding_percent': ('Реклама у новинах, %', 'int', 100, 0, 100, 'brand', [0, 1, 50, 70, 90, 100], 'Частка придатних новин з підписом. 100 — у кожній; це не скасовує фільтри реклами нижче.'),
    'market_branding_percent': ('Реклама у цінових алертах, %', 'int', 100, 0, 100, 'brand', [0, 50, 90, 100], 'Окрема частка для BTC/ETH/SOL.'),
    'branding_ai_percent': ('Фрази від AI, %', 'int', 80, 0, 100, 'brand', [0, 1, 50, 80, 100], 'У режимі «Автоматично»: 0 — тільки шаблони, 100 — завжди пробувати AI; невдала фраза замінюється шаблоном.'),
    'branding_quote': ('Реклама як цитата', 'bool', True, None, None, 'brand', [], 'Вимкніть для звичайного текстового підпису.'),
    'branding_skip_sensitive': ('Без реклами під трагедіями', 'bool', True, None, None, 'brand', [], 'Прибирає рекламу, якщо модель або фільтр визначили трагічну чи надзвичайну подію.'),
    'branding_skip_score': ('Без реклами від оцінки', 'int', 98, 0, 101, 'brand', [0, 90, 98, 100, 101], '101 — не прибирати рекламу через оцінку. 0 — прибирати в усіх новинах. Не стосується ринкових алертів.'),
    'branding_text': ('Власний рекламний текст', 'text', '', 0, 800, 'brand', [], 'До 800 символів російською. Без HTML та URL. FINDOLLAR буде клікабельним.'),
    'brand_name': ('Назва бренду', 'text', 'FINDOLLAR', 1, 50, 'brand', [], 'Клікабельна назва в рекламному підписі, до 50 символів.'),
    'brand_url': ('Посилання бренду', 'url', 'https://t.me/findollarapp', 1, 2000, 'brand', [], 'Публічне посилання http:// або https://.'),
    'market_enabled': ('Усі цінові алерти', 'bool', True, None, None, 'market', [], 'Головний перемикач BTC/ETH/SOL; новини працюють окремо.'),
    'max_title_chars': ('Довжина заголовка, символи', 'int', 160, 1, 300, 'content', [40, 80, 160, 300], 'Максимальна довжина заголовка.'),
    'max_body_chars': ('Довжина новини, символи', 'int', 850, 1, 2500, 'content', [200, 500, 850, 1500, 2500], 'Максимальна довжина основного тексту; підпис і джерела мають вміститися в ліміт Telegram.'),
    'max_source_links': ('Джерел у пості', 'int', 3, 0, 10, 'content', [0, 1, 2, 3, 5, 10], 'Кількість клікабельних джерел; 0 — приховати блок у пості. Перевірка джерел залишається.'),
    'photos_enabled': ('Додавати дозволені фото', 'bool', True, None, None, 'content', [], 'Лише фото з підтвердженим дозволом на повторне використання.'),
    'news_style': ('Побажання до стилю новин', 'text', '', 0, 1000, 'content', [], 'Наприклад: «Пиши дуже коротко, пояснюй користь для підприємця». Мова постів залишається російською; факти не вигадуються.'),
    'feed_max_age_hours': ('Вік статті RSS, години', 'float', 5, 0, 720, 'sources', [0, 1, 5, 12, 24, 72], '0 — не обмежувати датою статті. Велике значення може пропускати старі новини.'),
    'evidence_max_age_hours': ('Вік зібраних підтверджень, години', 'float', 8, 0, 720, 'sources', [0, 2, 8, 24, 72], '0 — без цього обмеження; старі дані все одно поступово виходять із кешу.'),
    'max_items_per_feed': ('Нових статей з одного RSS', 'int', 15, 1, 500, 'sources', [1, 5, 15, 50, 100], 'Максимум нових статей від одного джерела за перевірку.'),
    'max_ai_articles': ('Статей на аналіз AI', 'int', 55, 1, 1000, 'sources', [10, 25, 55, 100, 240], 'Більше статей — більше навантаження й витрат квоти AI. Може впертися в ліміт провайдера.'),
    'article_cache_limit': ('Статей у кеші', 'int', 240, 1, 5000, 'sources', [50, 240, 500, 1000], 'Кеш дозволяє знаходити підтвердження між запусками.'),
}
MARKET_OPTIONS = {
    'enabled': ('Цей алерт увімкнено', 'bool', True, None, None, 'market', [], 'Окремий перемикач монети та періоду.'),
    'threshold_percent': ('Поріг зміни, %', 'float', 5, 0, 10000, 'market', [0, 1, 3, 5, 10], '0 — будь-який рух; повтори ще обмежуються паузою й додатковою зміною.'),
    'cooldown_hours': ('Пауза повторного алерта, год', 'float', 3, 0, 8760, 'market', [0, 0.5, 1, 3, 6, 24], '0 — без часової паузи для повтору.'),
    'renotify_extra_percent': ('Додаткова зміна для повтору, %', 'float', 3, 0, 10000, 'market', [0, 1, 3, 5, 10], 'Після першого алерта рух має посилитися на стільки відсоткових пунктів. 0 — без додаткового кроку.'),
    'urgent_percent': ('Рух для термінового звуку, %', 'float', 10, 0, 10000, 'market', [0, 5, 10, 15, 50], '0 — кожен алерт терміновий. Нічний режим може заборонити звук навіть терміновим.'),
    'reset_ratio': ('Скидання епізоду: частка порога', 'float', 0.6, 0, 1, 'market', [0, 0.3, 0.6, 1], 'За частки 0.6 і порога 5% епізод скидається, коли рух стає меншим за 3%.'),
}
GROUPS = {'news': '📰 Ліміти й важливість', 'brand': '💚 Деталі реклами', 'quiet': '🌙 Тиша та терміновість',
          'content': '✍️ Текст і фото', 'sources': '📚 Збір новин', 'market': '💰 Алерти'}
ALIASES = {'limit': 'max_regular_per_day', 'gap': 'min_post_gap_minutes',
           'threshold': 'importance_threshold', 'perrun': 'max_posts_per_run',
           'ads': 'branding_percent', 'aiads': 'branding_ai_percent'}


def validate(name, value, market=False):
    spec = (MARKET_OPTIONS if market else OPTIONS).get(name)
    if not spec:
        raise ValueError('Невідомий параметр.')
    label, kind, default, low, high, *_ = spec
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        if str(value).lower() in ('true', 'on', '1'):
            return True
        if str(value).lower() in ('false', 'off', '0'):
            return False
        raise ValueError(label + ': оберіть увімкнути або вимкнути.')
    if kind in ('int', 'float'):
        try:
            if isinstance(value, bool):
                raise ValueError()
            result = float(str(value).replace(',', '.'))
            if not math.isfinite(result) or not low <= result <= high or (kind == 'int' and not result.is_integer()):
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f'{label}: введіть ' + ('ціле число' if kind == 'int' else 'число') +
                             f' від {low} до {high}.') from None
        return int(result) if kind == 'int' else result
    value = str(value).strip()
    if not low <= len(value) <= high:
        raise ValueError(f'{label}: довжина від {low} до {high} символів.')
    if kind == 'url':
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('Потрібне http:// або https:// посилання без логіна чи пароля.')
    return value
