# -*- coding: utf-8 -*-
"""Manual PETS 3.1.1 source-only dry-run. No AI and no Telegram calls."""
import json
import os

from case_pipeline import config
from case_pipeline.pets_candidates import (FdaCvmSafetyAdapter, FrontiersVeterinaryPmcAdapter,
                                            PmcOpenAccessAdapter, collect_source_candidates)
from case_pipeline.pets_storage import PetsStorage


SOURCE_ROLES = {
    "pmc_oa": {"role": "automatic_source", "rule": "full text + confirmed reuse licence required"},
    "frontiers_vet": {"role": "automatic_source", "rule": "full text via PMC OA + confirmed reuse licence required"},
    "fda_cvm": {"role": "safety_signal_only", "rule": "never convert a recall into an owner recommendation"},
    "wsava": {"role": "fact_check_or_manual_review", "rule": "do not automatically copy or adapt protected guidance"},
    "aaha": {"role": "fact_check_or_manual_review", "rule": "do not automatically copy or adapt protected guidance"},
    "cat_friendly_homes": {"role": "fact_check_or_manual_review", "rule": "do not automatically copy or adapt protected guidance"},
}


def _serializable(candidate):
    result = dict(candidate)
    result["facts"] = [fact.serializable() for fact in candidate.get("facts", ())]
    return result


def run(limit=10, output_dir=None, db_path=None):
    output_dir = output_dir or config.RUNS_DIR
    db_path = db_path or config.PETS_CANDIDATES_DB_PATH
    st = PetsStorage(db_path)
    adapters = {
        "frontiers_vet": FrontiersVeterinaryPmcAdapter(),
        "pmc_oa": PmcOpenAccessAdapter(),
        "fda_cvm": FdaCvmSafetyAdapter(),
    }
    candidates, report, collection = collect_source_candidates(adapters, storage=st, limit=limit)
    ready = [item for item in candidates if item.get("editorial_status") == "editorially_ready"]
    review = [item for item in candidates if item.get("editorial_status") != "editorially_ready"]
    os.makedirs(output_dir, exist_ok=True)
    payload = {"dry_run": True, "telegram_published": 0, "gigachat_calls": 0,
               "candidate_count": len(ready), "review_count": len(review), "source_report": report,
               "collection": collection, "rejection_statistics": st.source_rejection_statistics(),
               "source_roles": SOURCE_ROLES,
               "candidates": [_serializable(item) for item in ready],
               "review_candidates": [_serializable(item) for item in review]}
    with open(os.path.join(output_dir, "pets_source_candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
    with open(os.path.join(output_dir, "pets_source_candidates_diagnostics.json"), "w", encoding="utf-8") as fh:
        json.dump({"source_report": report, "collection": collection, "candidate_count": len(ready),
                   "review_count": len(review), "rejection_statistics": st.source_rejection_statistics()}, fh,
                  ensure_ascii=False, indent=2, sort_keys=True)
    return payload


if __name__ == "__main__":
    configured = int(os.getenv("PETS_SOURCE_CANDIDATE_LIMIT", "10"))
    if not 1 <= configured <= 10:
        raise SystemExit("PETS_SOURCE_CANDIDATE_LIMIT must be in 1..10")
    run(limit=configured)
