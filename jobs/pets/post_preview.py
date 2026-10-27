# -*- coding: utf-8 -*-
"""Manual PETS 3.2 post-preview entry point; never sends Telegram."""
import os

from case_pipeline.pets_post_preview import build_preview


if __name__ == "__main__":
    build_preview(os.getenv("PETS_POST_PREVIEW_DIR", "runs/pets_post_preview"),
                  use_live_gigachat=os.getenv("PETS_32_USE_LIVE_GIGACHAT", "0") == "1",
                  owner_approved=os.getenv("PETS_32_OWNER_APPROVED", "0") == "1",
                  download_image=True)
