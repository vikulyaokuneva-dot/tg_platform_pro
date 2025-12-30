
import time, json, hashlib, traceback
from pathlib import Path
import importlib.util
import feedparser
import schedule
from telegram import Bot

BASE_DIR = Path(__file__).parent.parent
CHANNELS_DIR = BASE_DIR / "channels"

def load_channels():
    channels = []
    for d in CHANNELS_DIR.iterdir():
        if not d.is_dir():
            continue
        cfg_path = d / "config.py"
        if not cfg_path.exists():
            continue

        spec = importlib.util.spec_from_file_location(d.name, cfg_path)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)

        if hasattr(cfg, "ENABLED") and not cfg.ENABLED:
            continue

        channels.append({"name": d.name, "config": cfg, "dir": d})
    return channels

def load_storage(ch):
    path = ch["dir"] / "storage.json"
    if not path.exists():
        return {"posted": []}
    return json.loads(path.read_text())

def save_storage(ch, data):
    (ch["dir"] / "storage.json").write_text(json.dumps(data, indent=2))

def make_uid(entry):
    base = entry.get("id") or entry.get("link") or entry.get("title")
    return hashlib.md5(base.encode()).hexdigest()

def format_post(entry):
    title = entry.get("title", "")
    link = entry.get("link", "")
    summary = entry.get("summary", "")[:500]
    return f"🔥 <b>{title}</b>\n\n{summary}\n\n<a href='{link}'>Источник</a>"

def post_cycle(ch):
    cfg = ch["config"]
    bot = Bot(token=cfg.BOT_TOKEN)
    storage = load_storage(ch)

    for rss in cfg.RSS_SOURCES:
        feed = feedparser.parse(rss)

        for entry in feed.entries[:cfg.MAX_POSTS_PER_CYCLE]:
            uid = make_uid(entry)
            if uid in storage["posted"]:
                continue
            try:
                text = format_post(entry)
                bot.send_message(
                    chat_id=cfg.CHAT_ID,
                    text=text,
                    parse_mode="HTML"
                )
                storage["posted"].append(uid)
                save_storage(ch, storage)
                time.sleep(cfg.POST_DELAY)
            except Exception:
                traceback.print_exc()

def run():
    channels = load_channels()
    print(f"🚀 Loaded {len(channels)} channels")

    for ch in channels:
        schedule.every(ch["config"].INTERVAL_MINUTES).minutes.do(post_cycle, ch)

    while True:
        schedule.run_pending()
        time.sleep(5)
