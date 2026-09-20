# -*- coding: utf-8 -*-
"""Release stuck claim and retry publish with longer timeouts."""
import sys, os
sys.path.insert(0, ".")
from case_pipeline import storage as storage_mod

st = storage_mod.Storage("data/agro_channel.db")
rows = st.db.execute(
    "SELECT id, canonical_url, status FROM materials WHERE status='publishing' ORDER BY id DESC LIMIT 1"
).fetchone()
if rows:
    mid, url, status = rows
    print(f"Releasing mid={mid} url={url[:60]} status={status}")
    st.release_claim(mid, status="post_ready", reason="timeout retry")
    print("Released to post_ready")
else:
    print("No publishing rows found")
