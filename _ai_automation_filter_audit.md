# AI Automation filter audit (read-only before edit)
TARGET CHANNEL: ai_automation (news + case pipeline, NOT AGRO — untouched)
DB: data/ai_case_pipeline.db  materials: post_ready=59, review=21, published=4

HARD FAIL — keep (spam / empty / dup / critical error):
- pipeline.py:81-83  dup / extraction failed -> rejected
- pipeline.py:85-89  quality==poor -> review (preserved; not auto-rejected again)
- pipeline.py:98-105  classify exception -> failed
- pipeline.py:133-136  cls_type!=business_case -> rejected (rules gateway — for AI Automation allow how_to/news via AI arbitration, not hard reject; see change plan)
- postgen.validate_post:288-302  invented numbers / hype / missing company / bad length / editorial -> review
- evidence.validate_case (not edited here) — source-confirmed evidence required

SOFT CHECK — over-strict for AI Automation (to be relaxed):
- case_model.py:333-349 validate_case_shape
    * REQUIRED_FIELDS all 6 (case_id, url, company_name, problem, impl, evidence) -> fails practical guides without named company/metric
    * line 347-349: numeric = metrics OR results with digits -> NO NUMERIC = error -> rejects practical instructions, workflow guides, tool reviews, agent how-tos
- pipeline.py:111-132 needs_review: AI arbitration only accepts business_case with quotes; how_to/news/review -> review/rejected — should allow how_to/workflow via soft check
- ai.py SYSTEM + validate_verdict (line 62-82): business_case requires problem_quote+implementation_quote; excludes practical AI instructions / automation breakdowns with no single company case
- news.py:143  len(text) < NEWS_MIN_CHARS(400); news.py:154 age>7d; news.py:148 AI-related relevance; news.py:163 duplicate/published — keep for news lane, soften MIN/age only for practical content

AGRO STATUS (NOT TOUCHED): case_pipeline/agro.py source missing, reconstructed _agro_decompiled.py only; data/agro_channel.db (failed=1,new=18,published=1) unchanged; no workflow edit.
