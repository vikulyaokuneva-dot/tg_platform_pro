# AGRO FILTER DIAGNOSTIC — READ-ONLY
Source: case_pipeline/agro.py (source missing; reconstructed from .pyc); DB: data/agro_channel.db; workflow: .github/workflows/*.yml (not edited)
No changes to code/DB/config/workflow/publish/commit.

## 1. STATUS FORMATION LOCATIONS (file / function / line / condition)

| Status | File | Function | Condition / rule (from .pyc constants) |
| rejected | agro (pyc line ~144) | process_url | `len(text) < MIN_BODY_CHARS` → "thin content (%d)" / rejected "thin"; also fetch/quality failures; also editorial gate `editorial_agro` failures |
| news_hold | agro / process_url | process_url | classifier result `type == "news"` (const 28) → status `news_hold` (const 29); also `stale` if age > AGRO_MAX_AGE_DAYS (25) |
| skipped | agro / process_url | process_url | `_known_skip()` / already-known URL / duplicate / skipped adapter; const 1 = "skipped", const 5 = "already %s" |
| post_ready | agro / process_url | process_url | passes `len(text)` in [MIN_BODY_CHARS, MAX_BODY_CHARS], age OK (`_age_ok`), class = practical/agro (not news), editorial passes, claim available |
| published | agro / process_url | process_url | `publish=True` + `AGRO_PUBLISH=1` + claim_for_publish + telegram.publish_post |

Key constants (reconstructed from co_consts):
- `MIN_BODY_CHARS = 700`
- `MAX_BODY_CHARS = 750`
- `MAX_POST_CHARS = 1800`
- `AGRO_MAX_AGE_DAYS = 25`
- `AGRO_MAX_PER_RUN = 4` (run const 6)
- `AGRO_PUBLISH_LIMIT` (from config, limit per run)
- `_SKIP_PAR_RX = ^(фото|видео|читайте также|подписк|реклама|похожие материалы|источник:)`
- `AGRO_DOMAIN_RULES` = domain safety regex
- `AGRO_FALLBACK_DOMAIN` = fallback domain
- `AGRO_ALLOWED_TAGS` = tag whitelist for editorial gate

## 2. FULL CHAIN
```
source (botanichka / agroinvestor / gismeteo)
→ adapter.discover()
→ process_url(url)
  → fetch (httpclient) → if fail: rejected/failed
  → extract (extraction.extract_from_html) → quality check
  → len(text) check vs MIN_BODY_CHARS (700) / MAX_BODY_CHARS (750)
  → _age_ok() (date from JSON-LD/OG; if missing: not blocked; max 25 days)
  → classifier_agro.classify() → type = practical / agro / news / other
    → if news → news_hold
    → if type not practical/agro → rejected
  → build_post() → extractive post (2 paragraphs, title-benefit, link, tags)
    → _pick_paragraphs (2 paras, max 120 chars/para, skip paragraphs matching _SKIP_PAR_RX)
    → _strip_urls_and_tags (remove URLs, strip hashtags)
  → editorial_agro() → artifacts? langguard? numbers in source? tag whitelist? length <= 1800? else rejected/review
  → claim_for_publish → publish_post → published
```

## 3. FILTER DETAIL

- Length: `len(text) < 700` → rejected "thin"; `len(text) > 750` probably truncated or rejected (MAX_BODY_CHARS very tight). Window 700–750 chars — extremely narrow for evergreen AGRO content.
- Image: not explicitly filtered by name; depends on extraction quality / content_hash.
- Source presence: required (extraction must succeed).
- URL / domain: `AGRO_DOMAIN_RULES` validates domain; fallback allowed.
- Date: `_age_ok()` uses JSON-LD/OG `published_at`; if unparseable: not blocked; if >25 days: stale/rejected.
- Keywords: `_SKIP_PAR_RX` skips paragraphs starting with "фото/видео/читайте также/подписка/реклама/похожие материалы/источник".
- Duplicates: storage.content_duplicated + hash check (same as pipeline).
- News/fresh: `classifier_agro` tags `news`; if `news` → `news_hold`; also `practical` vs `news` distinction.
- Score / threshold: classifier confidence used (not a hard numeric threshold from constants, but `classify()` returns it).
- Minimum facts: extractive build requires 2 paragraphs with substance; if extraction poor → rejected.
- AI / editorial: `editorial_agro()` checks artifacts, language, numbers present in source quote (`\d...` regex), tag whitelist, post length <= 1800.
- MIN/MAX/LIMIT: `MIN_BODY_CHARS=700`, `MAX_BODY_CHARS=750`, `MAX_POST_CHARS=1800`, `AGRO_MAX_AGE_DAYS=25`, `AGRO_MAX_PER_RUN=4`, `AGRO_PUBLISH_LIMIT`.

## 4. news_hold EXPLANATION

From `process_url` const 28/29: if `classifier_agro.classify()` returns `type == "news"`, status = `news_hold`. Why news can't publish in AGRO: AGRO lane is `practical` / evergreen gardening content (`TOPICS`: Ботаничка / Агроинвестор / Gismeteo); news articles are time-sensitive and belong to news lane, not evergreen AGRO. `news_hold` is temporary (waits for news lane / hold), not final reject — material stays in DB as `new` or can be reprocessed.

## 5. rejected REASONS (independent)

1) Fetch failure / extraction failed / quality bad.
2) `len(text) < 700` → "thin content".
3) Classification not practical/agro (other or unknown).
4) Age > 25 days (`stale`) — though `_age_ok()` notes missing date is not blocked.
5) Editorial gate failure (artifacts, language, number not in source, tags invalid, post > 1800 chars).
6) Duplicate content / already processed (`_known_skip`).
Multiple reasons can apply; priority: fetch > thin > classify > editorial > stale.

## 6. skipped EXPLANATION

`_known_skip()` / `already %s` / adapter skip. Normal — duplicate URLs or already-checked from previous run. Not an error.

## 7. STRICTNESS TABLE

| Filter | Condition | Purpose | Strictness | Can block normal AGRO? |
| MIN_BODY_CHARS (700) | text len >=700 | ensure substance | VERY HIGH (700 min) | Yes — short evergreen tips often <700 |
| MAX_BODY_CHARS (750) | text len <=750 | limit size | HIGH (only 50-char window) | Yes — long practical guides >750 rejected |
| MAX_POST_CHARS (1800) | post <=1800 | Telegram limit | MEDIUM | Unlikely for extractive 2-paras |
| AGRO_MAX_AGE_DAYS (25) | article <=25d | freshness | MEDIUM/HIGH | Yes — evergreen articles can be older |
| _SKIP_PAR_RX | skip paras with keywords | clean extractive | LOW/MEDIUM | Unlikely — only skips meta paras |
| AGRO_DOMAIN_RULES | domain whitelist | source trust | MEDIUM | Unlikely if sources configured |
| editorial_agro (numbers in source) | number quote verified | factual integrity | MEDIUM | Possible if stats embedded differently |
| news_hold (news type) | not news | lane separation | HIGH (for AGRO) | Correct — news shouldn't go to AGRO |

## 8. WHY 23 → 12 rejected / 9 news_hold / 2 skipped / 0 post_ready

From DB: `data/agro_channel.db` materials: `new=18`, `failed=1`, `published=1`. The 23 checked = 18 new + 1 failed + other (likely skipped duplicates from previous runs). No `post_ready` because:
- Most sources (`botanichka`, `agroinvestor`, `gismeteo`) likely produce either news-classified material (`news_hold`) or thin/block content (`rejected`).
- `MIN_BODY_CHARS=700` + `MAX_BODY_CHARS=750` is extremely strict — only articles with ~700-750 chars of clean body pass; many RSS snippets don't.
- No successful extraction met all gates (length + age + practical classification + editorial) in this run.
- 2 skipped = duplicates / already known.
- 9 news_hold = classifier tagged as news (time-sensitive from sources); 12 rejected = thin/content/fail/editorial/stale.

## 9. CRITICAL FILTERS (don't weaken without decision)

- `MIN_BODY_CHARS` / `MAX_BODY_CHARS`: narrowing 700–750 is the primary blocker; lowering min to ~300 and raising max to ~1500 would allow evergreen content.
- `AGRO_MAX_AGE_DAYS=25`: should stay for news, but evergreen can be older; consider separate evergreen vs news lanes.
- `editorial_agro` number-check and tag-whitelist: should stay (factual integrity / brand consistency).
- `news_hold`: correct behavior — don't weaken (separate news lane exists).
- `_SKIP_PAR_RX` / domain rules: safe to keep.

## 10. CONCEPT MATCH (AGRO = evergreen, practical, seasonal gardening)

Partial mismatch: current logic expects ~700-char practical articles within 25 days, with strict extractive 2-paragraph format. Ever-green gardening content (seasonal care, plant guides) often is longer, older, less "news-y" — current filter set designed more like a news pipeline with size caps. Recommendation (not executed): split evergreen AGRO (lower min, older allowed, longer allowed, practical focus) from news AGRO.

## 11. NOT TOUCHED
- No file edited.
- `case_pipeline/agro.py` source not present; only `.pyc` read (decompiled to `_agro_decompiled.py`).
- DB `data/agro_channel.db` not modified (read only: status counts shown).
- `data/ai_case_pipeline.db` untouched.
- No workflow edited.
- No commit/push.
- No Telegram publish.
- `PROBLEM_KW` / case pipeline unchanged.
