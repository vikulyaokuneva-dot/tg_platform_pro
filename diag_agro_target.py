# -*- coding: utf-8 -*-
"""TEMPORARY: диагностика agro-target перед запуском пайплайна в CI.

Что печатает (БЕЗ секретов):
  * AGRO_CHAT_ID: длина, sha256-префикс, первые/последние 4 символа, repr
    (в CI GitHub маскирует точное значение секрета как ***, но
    длина/хеш/фикстуры остаются — этого достаточно для сверки со значением
    -1003389902213: len=14 sha256_16=797df0e849a9e310);
  * AGRO_BOT_TOKEN: ТОЛЬКО длина и sha256-префикс (сам токен и фрагменты
    не печатаются никогда; сверка локального токена: len=46
    sha256_16=465f144095c40edf);
  * getMe(AGRO_BOT_TOKEN) -> id/username бота (ожидаем 8285212740 /
    @shared_platform_bot);
  * getChat(AGRO_CHAT_ID) -> ok/description + id/type/title/username чата;
  * getChatMember(AGRO_CHAT_ID, bot_id) -> status (ожидаем administrator);
  * read-only дамп terminal-строк data/agro_channel.db (статусы/причины) —
    видно, опубликована ли уже статья и какие URL зависли в review.

Скрипт НЕ падает (всегда exit 0) и НЕ должен блокировать шаг пайплайна.
Ошибки запросов печатаются только по типу/санитизированному тексту
(токен вырезается из любого сообщения исключения).
"""
import hashlib
import os
import sqlite3
import sys

import requests

from case_pipeline import config

API = "https://api.telegram.org/bot%s/%s"
KNOWN_CHAT_SHA = "797df0e849a9e310"      # sha256("-1003389902213")[:16]
KNOWN_TOKEN_SHA = "465f144095c40edf"     # sha256(токена из .env, len=46)[:16]


def sha16(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def safe(msg, token):
    return str(msg).replace(token or "", "***")


def main():
    token = config.AGRO_BOT_TOKEN or ""
    chat = config.AGRO_CHAT_ID or ""

    print("== agro target diag (TEMPORARY) ==")
    # --- chat id (не token: печатаем всё, но GitHub замаскирует секрет) ---
    print("AGRO_CHAT_ID: value=%r len=%d sha256_16=%s first4=%r last4=%r"
          % (chat, len(chat), sha16(chat), chat[:4], chat[-4:]))
    print("  expected good: len=14 sha256_16=%s first4='-100' last4='2213'"
          % KNOWN_CHAT_SHA)
    print("  match_known_good=%s" % (len(chat) == 14 and sha16(chat) == KNOWN_CHAT_SHA))
    # --- token: НИКАКИХ значений/фрагментов, только метрики ---
    print("AGRO_BOT_TOKEN: set=%s len=%d sha256_16=%s (value NOT printed)"
          % (bool(token), len(token), sha16(token) if token else "-"))
    print("  expected local token: len=46 sha256_16=%s match=%s"
          % (KNOWN_TOKEN_SHA, len(token) == 46 and sha16(token) == KNOWN_TOKEN_SHA))

    def call(method, params=None):
        try:
            r = requests.get(API % (token, method), params=params or {}, timeout=25)
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, {"ok": False, "description": "non-JSON"}
        except Exception as e:
            return None, {"ok": False, "description": "EXC " + type(e).__name__
                          + ": " + safe(e, token)}

    # --- getMe(AGRO_BOT_TOKEN) ---
    st, me = call("getMe")
    res = me.get("result") or {}
    print("getMe: http=%s ok=%s id=%s username=%s first_name=%r description=%s"
          % (st, me.get("ok"), res.get("id"), res.get("username"),
             res.get("first_name"), safe(me.get("description") or "", token)))
    bot_id = res.get("id")
    print("  expected bot: id=8285212740 username=shared_platform_bot match=%s"
          % (bot_id == 8285212740))

    # --- getChat(AGRO_CHAT_ID) ---
    st, gc = call("getChat", {"chat_id": chat})
    c = gc.get("result") or {}
    print("getChat(AGRO_CHAT_ID): http=%s ok=%s description=%s"
          % (st, gc.get("ok"), safe(gc.get("description") or "", token)))
    print("  chat: id=%s type=%s title=%r username=%s"
          % (c.get("id"), c.get("type"), c.get("title"), c.get("username")))
    print("  expected chat: id=-1003389902213 type=channel username=helpgardener "
          "match=%s" % (str(c.get("id")) == "-1003389902213"))

    # --- getChatMember(AGRO_CHAT_ID, bot) ---
    if bot_id and chat:
        st, gm = call("getChatMember", {"chat_id": chat, "user_id": bot_id})
        print("getChatMember(bot in chat): http=%s ok=%s status=%s description=%s"
              % (st, gm.get("ok"),
                 (gm.get("result") or {}).get("status") if gm.get("ok") else None,
                 safe(gm.get("description") or "", token)))

    # --- can_post_messages ( Bot API getChatAdministratorPermissions ) ---
    if bot_id and chat:
        st, gp = call("getChatAdministratorPermissions",
                      {"chat_id": chat, "user_id": bot_id})
        if gp.get("ok"):
            p = gp.get("result") or {}
            print("getChatAdministratorPermissions: can_post_messages=%s "
                  "can_edit_messages=%s" % (p.get("can_post_messages"),
                                            p.get("can_edit_messages")))
        else:
            print("getChatAdministratorPermissions: http=%s ok=False description=%s"
                  % (st, safe(gp.get("description") or "", token)))

    # --- тот же ТОКЕН против AI-канала: общий secret безопасно ли менять? ---
    ai_chat = config.CHAT_ID or ""
    st, ga = call("getChat", {"chat_id": ai_chat})
    a = ga.get("result") or {}
    print("getChat(AI %r): http=%s ok=%s description=%s"
          % (ai_chat, st, ga.get("ok"), safe(ga.get("description") or "", token)))
    print("  ai chat: id=%s type=%s title=%r" % (a.get("id"), a.get("type"),
                                                 a.get("title")))
    if bot_id and ai_chat:
        st, gm2 = call("getChatMember", {"chat_id": ai_chat, "user_id": bot_id})
        print("getChatMember(bot in AI chat): http=%s ok=%s status=%s description=%s"
              % (st, gm2.get("ok"),
                 (gm2.get("result") or {}).get("status") if gm2.get("ok") else None,
                 safe(gm2.get("description") or "", token)))

    # --- read-only: terminal-строки агро-БД (риск повторной публикации) ---
    db_path = config.AGRO_DB_PATH
    print("agro db: %s exists=%s" % (db_path, os.path.exists(db_path)))
    if os.path.exists(db_path):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % db_path.replace("\\", "/"),
                                  uri=True)
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT id,status,telegram_message_id,substr(reason,1,80) r,"
                "substr(url,1,90) u FROM materials"
                " WHERE status IN ('published','review','post_ready','publishing')"
                " ORDER BY id DESC LIMIT 20").fetchall()
            print("terminal rows (%d):" % len(rows))
            for r in rows:
                print("  #%s %s mid=%s %s | %s" % (
                    r["id"], r["status"], r["telegram_message_id"],
                    r["r"], r["u"]))
            fos = con.execute(
                "SELECT id,status FROM materials"
                " WHERE url LIKE '%fosfor-dlya-yagodnika%'").fetchall()
            print("fosfor-dlya-yagodnika in CI db: %s"
                  % ([tuple(f) for f in fos] or "ABSENT"))
            pubs = con.execute(
                "SELECT id,material_id,telegram_message_id,ok,"
                "substr(published_at,1,20) t FROM publications"
                " ORDER BY id DESC LIMIT 5").fetchall()
            print("publications tail: %s" % [tuple(p) for p in pubs])
            con.close()
        except Exception as e:
            print("db dump error: %s" % safe(e, token))

    print("== end diag ==")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:   # диагностика никогда не должна ронять пайплайн
        print("diag fatal: %s" % type(e).__name__)
        sys.exit(0)
