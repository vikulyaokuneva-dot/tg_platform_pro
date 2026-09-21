# RECONSTRUCTED FROM agro.cpython-312.pyc (read-only)
# Source file: case_pipeline/agro.py (source missing; only .pyc exists)

MODULE NAMES (co_names): ('__doc__', 'logging', 're', 'datetime', 'timedelta', 'timezone', '', 'adapters', 'case_model', 'classifier_agro', 'config', 'extraction', 'hashtags', 'httpclient', 'langguard', 'storage', 'storage_mod', 'telegram', 'textclean', 'utils', 'getLogger', 'log', 'SOURCE_LABELS', 'TOPICS', 'AGRO_DOMAIN_RULES', 'AGRO_FALLBACK_DOMAIN', 'AGRO_ALLOWED_TAGS', 'MIN_BODY_CHARS', 'MAX_BODY_CHARS', 'MAX_POST_CHARS', 'compile', 'I', '_SKIP_PAR_RX', '_age_ok', '_cut_sentences', '_pick_paragraphs', 'build_post', 
CONSTANTS preview (first 20):
  0: str(len=889) -> case_pipeline.agro — второй канал (jobs/agro): агро-практика.

Линия контента над общим ядром — структурный аналог news.py (у платформы уже
есть прецедент lanes: case-пайплайн + «Новости дня»). Ядро и
  1: int=0
  2: <class 'NoneType'>=None
  3: <class 'tuple'>=('datetime', 'timedelta', 'timezone')
  4: int=1
  5: <class 'tuple'>=('adapters', 'case_model', 'classifier_agro', 'config', 'extraction', 'hashtags'
  6: str(len=9) -> case.agro
  7: str(len=9) -> Ботаничка
  8: str(len=12) -> Агроинвестор
  9: str(len=8) -> Gismeteo
  10: <class 'tuple'>=('botanichka', 'agroinvestor', 'gismeteo')
  11: str(len=5) -> #Агро
  12: int=700
  13: int=750
  14: int=1800
  15: str(len=71) -> ^(фото|видео|читайте также|подписк|реклама|похожие материалы|источник:)
  16: code=_age_ok
  17: code=_cut_sentences
  18: code=_pick_paragraphs
  19: code=build_post

===== SUB FUNCTION CONSTANTS =====

--- FUNCTION: _age_ok (line info available) ---
  const[0] = "Окно свежести по дате статьи (JSON-LD/OG). Дату не распарсили — не\n    блокируем (агрегаторы врут в метаданных чаще, чем публикуют старьё)."
  const[1] = True
  const[2] = "Z"
  const[3] = "+00:00"
  const[5] = 25
  const[6] = "(\d{4})-(\d{2})-(\d{2})"
  const[7] = 1
  const[8] = 2
  const[9] = 3
  names: ('str', 'strip', 'replace', 'datetime', 'fromisoformat', 'ValueError', 're', 'search', 'int', 'group', 'timezone', 'utc', 'tzinfo', 'now', 'timedelta', 'config', 'AGRO_MAX_AGE_DAYS')

--- FUNCTION: _cut_sentences (line info available) ---
  const[1] = "[.!?…]"
  const[2] = -1
  const[3] = " "
  const[4] = 1
  const[5] = 0
  const[6] = "…"
  names: ('len', 'list', 're', 'finditer', 'end', 'strip', 'rsplit')

--- FUNCTION: _pick_paragraphs (line info available) ---
  const[0] = "2 первых содержательных абзаца (дословно из текста источника),\n    единый ограниченный блок — оборот на границе предложения."
  const[1] = 0
  const[2] = "\n\s*\n"
  const[3] = ""
  const[4] = "\s+"
  const[5] = " "
  const[6] = 120
  const[7] = 2
  const[8] = "\n\n"
  names: ('re', 'split', 'sub', 'strip', 'len', '_SKIP_PAR_RX', 'match', 'append', 'MAX_BODY_CHARS', 'join', '_cut_sentences')

--- FUNCTION: build_post (line info available) ---
  const[0] = "Extractive-макет агро-поста (не похож на WB-кейс: заголовок-польза,\n    2 абзаца сути, ссылка, контролируемые рубрики)."
  const[1] = ""
  const[2] = ".!?… "
  const[3] = "\s+[—–]\s+[^—–]{2,30}$"
  const[4] = 0
  const[5] = 110
  const[7] = " "
  const[8] = 1
  const[9] = ",;:—– "
  const[10] = "topics"
  const[11] = "🌱"
  const[12] = 2500
  const[13] = "agro"
  const[15] = "Источник: %s"
  const[16] = "\n\n"
  names: ('textclean', 'clean', 'strip', 'rstrip', 're', 'split', 'len', 'rsplit', 'get', 'hashtags', 'build', 'SOURCE_LABELS', 'AGRO_DOMAIN_RULES', 'AGRO_FALLBACK_DOMAIN', '_pick_paragraphs', 'append', 'render', 'join')

--- FUNCTION: _strip_urls_and_tags (line info available) ---
  const[1] = "https?://\S+"
  const[2] = " "
  const[3] = "(?m)^#[^\n]*$"
  names: ('re', 'sub')

--- FUNCTION: editorial_agro (line info available) ---
  const[0] = "Редакционные гейты линии: артефакты, язык, числа ⊆ источника, теги —\n    только словарь, объём. (Числа при extractive-посте гарантированы\n    конструкцией — гейт проверяет регрессию, а не презумпцию.)"
  const[1] = "artifacts in post"
  const[2] = "langguard: %s"
  const[3] = ""
  const[4] = "\d[\d.,]{1,}"
  const[5] = "number not in source: %s"
  const[6] = "post too long: %d"
  const[7] = "\n"
  const[8] = 1
  const[9] = -1
  names: ('textclean', 'has_artifacts', 'append', 'langguard', 'guard', 'utils', 'ws_norm', 're', 'finditer', '_strip_urls_and_tags', 'group', 'len', 'MAX_POST_CHARS', 'rstrip', 'rsplit', 'split', 'hashtags', 'validate', 'AGRO_ALLOWED_TAGS', 'extend')

--- FUNCTION: _known_skip (line info available) ---
  names: ()

--- FUNCTION: process_url (line info available) ---
  const[0] = "Один материал агро-линии. -> dict(status, ...) как pipeline.process_candidate."
  const[1] = "skipped"
  const[2] = ""
  const[4] = "status"
  const[5] = "already %s"
  const[8] = "failed"
  const[9] = "fetch: %s"
  const[11] = 200
  const[13] = "fetch"
  const[14] = "text"
  const[16] = "quality"
  const[17] = "rejected"
  const[18] = "thin content (%d)"
  const[19] = "thin"
  const[20] = "published_at"
  const[21] = "stale: %s"
  const[22] = "stale"
  const[23] = "title"
  const[24] = "type"
  const[25] = "agro_type"
  const[26] = "confidence"
  const[27] = "practical"
  const[28] = "news"
  const[29] = "news_hold"
  names: ('add', 'get', '_known_skip', 'update', 'httpclient', 'fetch', 'config', 'FETCH_TIMEOUT_SEC', 'extraction', 'extract_from_html', 'FetchError', 'str', 'utils', 'content_hash', 'len', 'MIN_BODY_CHARS', '_age_ok', 'classifier_agro', 'classify', 'build_post', 'editorial_agro', 'join', 'claim_for_publish', 'telegram', 'publish_post', 'ok', 'mark_published', 'message_id', 'AGRO_CHAT_ID', 'case_model')

--- FUNCTION: run (line info available) ---
  const[0] = "Один цикл агро-канала. Публикация только publish=1 и AGRO_PUBLISH=1\n    (job передаёт), иначе — honest dry-run без отправки. Возвращает summary."
  const[1] = 0
  const[3] = "agro source %r: адаптер не зарегистрирован (см. отчёт)"
  const[4] = "agro discover %s failed: %s"
  const[6] = 4
  const[8] = "checked"
  const[9] = 1
  const[10] = "status"
  const[12] = "published"
  const[13] = "agro %s: %s %s"
  const[14] = 80
  names: ('storage_mod', 'Storage', 'config', 'AGRO_DB_PATH', 'AGRO_SOURCES', 'AGRO_MAX_PER_RUN', 'AGRO_PUBLISH', 'adapters', 'ADAPTERS', 'get', 'log', 'warning', 'discover', 'Exception', 'AGRO_PUBLISH_LIMIT', 'process_url', 'info')
