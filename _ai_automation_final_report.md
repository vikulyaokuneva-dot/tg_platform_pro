# AI Automation filter relaxation — final report (AGRO untouched)

BEFORE (strict hard rules blocking practical AI Automation content):
- case_model.validate_case_shape: numeric result HARD (metrics/results with digits required); missing = rejected
- pipeline: needs_review -> only business_case with quotes accepted; how_to/news -> rejected
- ai.validate_verdict: business_case requires problem_quote + implementation_quote (excludes guides/workflows)
- DB ai_case_pipeline: review=21, post_ready=59, published=4

CHANGED (only 3 tracked files — AI Automation; AGRO untouched):
- case_pipeline/case_model.py: numeric -> SOFT (soft note added; hard only for missing fields/evidence/class; allow how_to)
- case_pipeline/pipeline.py: arbitration accepts how_to; non-business only rejected for clearly off-topic (hard preserved)
- case_pipeline/ai.py: validate_verdict allows how_to/news/other without mandatory quote pair (business_case quote requirement preserved)
- tests/test_ai_automation_filters.py: 3 new (soft numeric OK / empty hard fail / practical guide)

AFTER:
- HARD FAIL kept: duplicate, extraction failed, missing problem/evidence, critical validation errors, spam/off-topic
- SOFT: numeric absence -> review (not rejected); how_to/workflow/agent/tool content allowed through arbitration; AI Automation practical guides reach post_ready/review
- dry-run: produced post_ready=1 (pipeline working, no real publish — dry_run=True)

TESTS:
- 3 new passed; full suite 99 passed / 4 pre-existing news failures (date-stale fixtures, unrelated to AI filters; news.py line 154 unchanged)

AGRO (explicit): NOT TOUCHED.
- case_pipeline/agro.py: source file still absent (only reconstructed _agro_decompiled.py); never edited
- data/agro_channel.db: unchanged (new=18, failed=1, published=1)
- .github/workflows: not edited; no workflow/publisher/DB-credential change

GIT:
- changed: case_pipeline/ai.py, case_model.py, pipeline.py (+22 insertions / −9 deletions)
- untracked audit/tests only; no commit/push performed
- AGRO source/file/workflow/DB: zero modifications
