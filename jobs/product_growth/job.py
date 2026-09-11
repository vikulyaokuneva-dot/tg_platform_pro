import os
import requests

def run(ctx):
    token = os.getenv("PRODUCT_GROWTH_BOT_TOKEN")
    chat_id = os.getenv("PRODUCT_GROWTH_CHAT_ID")

    if not token or not chat_id:
        ctx.log("❌ BOT_TOKEN or CHAT_ID not set")
        return

    if ctx.dry_run:
        ctx.log("DRY-RUN: message not sent")
        return

    text = "📰 Автопост от job-платформы"

    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        }
    )

    ctx.log(f"Telegram response: {r.status_code}")
