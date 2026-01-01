import os
import requests


def run(ctx):
    token = os.getenv("CRYPTO_AIRDROPS_BOT_TOKEN")
    chat_id = os.getenv("CRYPTO_AIRDROPS_CHAT_ID")

    # Проверка переменных окружения
    if not token or not chat_id:
        ctx.log("❌ CRYPTO_AIRDROPS_BOT_TOKEN or CRYPTO_AIRDROPS_CHAT_ID not set")
        raise RuntimeError("Telegram credentials missing")

    # DRY-RUN режим
    if getattr(ctx, "dry_run", False):
        ctx.log("⚠️ DRY-RUN enabled: message not sent")
        return

    text = "📰 Автопост от job-платформы"

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=15
        )
    except Exception as e:
        ctx.log(f"❌ Telegram request failed: {e}")
        raise

    # Логируем полный ответ Telegram
    ctx.log(f"Telegram status: {r.status_code}")
    ctx.log(f"Telegram response body: {r.text}")

    if r.status_code != 200:
        raise RuntimeError("Telegram message not sent")

    ctx.log("✅ Message successfully sent to Telegram")
