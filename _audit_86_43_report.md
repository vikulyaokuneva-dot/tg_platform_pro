# FORENSIC AUDIT — 86 and 43 (no code changed)

Source DB: data/ai_case_pipeline.db (post-rebuild; case_json unchanged for 86/43/90; rebuilt for 20/83 only)
No code edits. No regex change. Only inspection.

## MATERIAL 86 — Audit (from _audit_86.txt)

Source excerpt in DB (length 599): truncated; contains no full source body.
- `_sections(text)` keys: `[]` (empty)
- `case_sections` in DB: `['challenge', 'results', 'solution']` (pre-computed, not rebuilt from excerpt)
- `challenge content length`: 0 (no challenge text recoverable from excerpt)
- `_sec_sentences(challenge)`: 0 sentences
- Full sentences in excerpt (`_sentences`): 1 only
- `PROBLEM_KW` candidates (`_pick`): 0
- `IMPL_KW` candidates: 0
- `RESULT_KW` candidates: 0
- `problem == ''`: confirmed
ih
- `implementation` in DB: `How Learn It Live used an AI-powered chatbot to slash support tickets 40%` (title-like; matches `source_title` exactly)

### A — Does challenge section text exist in source?  
Unknown from DB excerpt alone (excerpt truncated at 599 chars, full source likely has it — `case_sections` records `challenge`). But `build_case()` cannot access it from `text` because `_sections(text)` sees empty headings.

### B — `_sec_sentences(sec["challenge"])`: 0 (section not present in `text` passed to `build_case`).

### C — `_pick()` doesn't use it because `_pick()` is called with `prefer=_sec_sentences(sec.get('problem'))` where `sec = _sections(text)`. Since `_sections(text) == {}`, `prefer` is `[]`. Candidates come only from full-body sentences (`sents`) — only 1 sentence in excerpt, which doesn't match `PROBLEM_KW`. So `_pick` returns empty.

### D — `implementation` gets title-like text: `_pick(sents, IMPL_KW, prefer=_sec_sentences(sec.get('solution')), exclude=problems)`. With no `solution` section found (`_sections` empty) and body truncated, `_pick` falls back to title/body merge; the longest match is the source title itself (`How Learn It Live...`). Confirmed by `is_title_like = True` (`first_impl[:60]` matches `source_title` prefix and starts with `How `).

**Root cause 86: A + C + D.** The `challenge` content exists in original source (evidenced by `case_sections`), but is not recoverable from `text`/`excerpt` used by `_sections()`. `_pick()` then has zero candidates. Implementation falls back to title text.

---

## MATERIAL 43 — Audit (from _audit_43.txt)

- `_sections(text)` keys: `[]` (same empty sections from truncated excerpt)
- `case_sections`: `['challenge', 'results', 'solution']` (pre-computed)
- `challenge content length`: 0
- `_sec_sentences(challenge)`: 0
- Full sentences (`_sentences`): 4 (more text survives than 86)
- `PROBLEM_KW` candidates: 1 (matches truncated body text: `Performance Marketing Manager at Synthesia... Challenge Synthesia's free AI tool...`)
- `IMPL_KW` candidates: 1 (`How Synthesia automates Facebook Conversions...` — title-like, `is_title_like = True`)
- `RESULT_KW` candidates: 1 (same merged title/body text)
- `problem == ''`: confirmed (no clean challenge sentence selected)
- `results == []`: confirmed (results not mapped properly; result content from `results` section lost)
- Numeric result: missing (`metrics` count 2 in DB from original build; rebuilt case_json not saved back for 43)

### Why `problem` empty despite candidate existing?

Candidate exists (`len=254`) from truncated body: it starts with title-like prefix (`Performance Marketing Manager at Synthesia`) and ends abruptly (`making i`). Because `_pick()` uses `quote_in_source(s, text)` filter (line 153 `case_model.py`), truncated/merged sentences may fail the literal quote verification against the truncated `text`. Even if it passes, `_pick()` picks only top 1 (`limit=2`) and the first may be excluded or mapped incorrectly when no `problem` section is present (`prefer` empty). In rebuilt DB for 43, `problem` remains `""`.

### Why `results == []`?
`_sections(text)` empty → `_sec_sentences('result')` empty → `sec_numbered = []`, `numbered = []` (no result sentences match strongly). Even though one `RESULT_KW` candidate exists (`How Synthesia automates...`), it's merged with title/body, starts with `How`, and is not a numeric result sentence. `results = sec_numbered[:2] or numbered or strong or res_pool[:2]` → empty because none of the conditions fill cleanly.

**Root cause 43: A + D.** Section mapping fails due to truncated excerpt (`_sections` empty); body candidates exist but are truncated/merged; result mapping fails because `results` section content not recoverable; `implementation` is title-like.

---

## COMPARISON WITH SUCCESSFUL MATERIALS (20, 83, 85)

| Material | `case_sections` | `sections_detected` | `problem` filled | `implementation` clean | Source domain / quality |
| 20 (fixed) | ['задача', 'результат', ... , 'решение'] | [problem, result, solution] | Yes | Yes | mindbox — full text available |
| 83 (fixed) | ['challenge', 'results', 'solution'] | [problem, result, solution] | Yes | Yes | zapier — full text available |
| 85 (published) | (previous) | — | Yes | Yes | — |
| 86 (broken) | ['challenge', 'results', 'solution'] | [problem, result, solution] | No | Title-like (`How Learn It Live...`) | zapier — excerpt truncated |
| 43 (broken) | ['challenge', 'results', 'solution'] | [problem, result, solution] | No | Title-like (`How Synthesia...`) | zapier — excerpt truncated |

**Common root cause for 86 and 43:**
- Both are Zapier sources (`zapier.com/customer-stories/...`).
- `case_sections` records `challenge`, `results`, `solution` (original source had them).
- `_sections(text)` on DB excerpt returns `[]` (truncated at 599 chars, headings lost).
- Without section headings, `_sec_sentences()` produces empty `prefer` lists for `problem` and `result`.
- `_pick()` relies on `prefer` + `quote_in_source()`; with empty prefer and truncated text, candidates either don't exist (86: 0) or exist but fail verification / are merged with title (43: 1 but rejected or mapped incorrectly).
- `implementation` always falls back to the source title because `_sections('solution')` is empty — the longest `IMPL_KW` match in truncated text is the article title starting with `How `<company>...

**Difference between 86 and 43:**
- 86: body excerpt very short (`_sentences` count = 1) → zero candidates for problem, result, implementation.
- 43: body excerpt longer (`_sentences` count = 4) → one truncated/merged candidate for each category; but because of `quote_in_source()` and missing `prefer` sections, none are selected cleanly into case fields.

## Root cause (single mechanism per material)

- **86:** Section mapping fails (`_sections` empty on truncated excerpt) → `_sec_sentences` produces zero sentences → `_pick` has zero candidates → `problem` and `results` empty; implementation defaults to title text (no `solution` section found).
- **43:** Same section mapping failure; longer excerpt produces truncated/merged body candidates; `problem` and `results` remain empty due to `quote_in_source()` filtering and missing clean `challenge`/`results` section sentences; `implementation` defaults to title.

**Common root cause:** Truncated `text`/`source_excerpt` (599 chars) loses section headings required by `_sections()`; `build_case()` then operates without section context, and `_pick()` either finds nothing or finds merged/truncated text that doesn't verify as a clean section quote.

## Recommended minimal fix (description only, no code change)

Rebuild of 86/43 requires either:
1) Re-fetching full source HTML and using the complete `text` for `_sections()` / `build_case()` (not just the truncated DB excerpt), or
2) Using the pre-computed `case_sections` content (if preserved separately) to restore section sentences directly, bypassing `_sections()` when the DB excerpt is truncated.

The `PROBLEM_KW` fix is not the blocker — 20 and 83 prove the regex works. The blocker for 86/43 is the **truncated source text used during rebuild**, which prevents `_sections()` from finding the `challenge`/`results` headings needed by `_pick()`.
