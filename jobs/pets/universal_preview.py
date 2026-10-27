# -*- coding: utf-8 -*-
"""Manual PETS 3.3 preview entry point; never sends Telegram."""
import os

from case_pipeline import config
from case_pipeline.ai import get_provider
from case_pipeline.pets_generator import GigaChatPetsGenerator
from case_pipeline.pets_universal_preview import build_previews


if __name__ == "__main__":
    use_live_gigachat = os.getenv("PETS_33_USE_LIVE_GIGACHAT", "0") == "1"
    owner_approved = os.getenv("PETS_33_OWNER_APPROVED", "0") == "1"
    max_gigachat_calls = int(os.getenv("PETS_33_MAX_GIGACHAT_CALLS", "1"))
    allow_live_ai = os.getenv("PETS_ALLOW_LIVE_AI", "0") == "1"
    # Provider construction stays behind all three independent opt-ins.  The
    # default preview is offline, and no secret/provider is touched in that path.
    generator = None
    if use_live_gigachat and owner_approved and allow_live_ai and max_gigachat_calls > 0:
        generator = GigaChatPetsGenerator(get_provider(), enabled=True)
    use_live_gigachat = use_live_gigachat and owner_approved and allow_live_ai
    build_previews(
        os.getenv("PETS_FACTUAL_BRIEFS_PATH", os.path.join(config.RUNS_DIR, "pets_source_candidates.json")),
        os.getenv("PETS_UNIVERSAL_PREVIEW_DIR", "runs/pets_universal_preview"),
        history_db_path=os.getenv("PETS_HISTORY_DB_PATH", config.PETS_DB_PATH),
        max_previews=int(os.getenv("PETS_UNIVERSAL_PREVIEW_LIMIT", "3")),
        use_live_gigachat=use_live_gigachat,
        owner_approved=owner_approved,
        max_gigachat_calls=max_gigachat_calls,
        generator=generator,
        download_images=os.getenv("PETS_UNIVERSAL_DOWNLOAD_IMAGES", "1") == "1",
    )
