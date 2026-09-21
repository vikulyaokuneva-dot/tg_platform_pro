# -*- coding: utf-8 -*-
"""case_pipeline.pipeline — оркестратор полного конвейера.

SOURCE → DISCOVERY → FETCH → EXTRACT → CLASSIFY (rules-first)
   ├─ business_case  → CASE → EVIDENCE-VALID → POST → [TELEGRAM]
   ├─ needs_review   → AI ARBITRATION (если доступен) → CASE/REVIEW
   └─ how_to/news/other → REJECT (лог)
Один кандидат не валит пайплайн; каждый имеет статус; артефакты в runs/<ts>/.
"""
import io
import json
import logging
import os
import re
import time

from . import adapters, ai, case_model, config, evidence, extraction, hashtags
from . import httpclient, langguard, news as news_mod, postgen, storage as storage_mod
from . import telegram
from .classifier_lib import V2
from .utils import content_hash, now_iso

log = logging.getLogger("case_pipeline")

TERMINAL = {"published", "case_built", "post_ready", "publishing", "rejected", "review"}


def _setup_logging(runs_dir):
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    try:
        fh = logging.FileHandler(os.path.join(runs_dir, "run.log"), encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt))
        logging.getLogger("case_pipeline").addHandler(fh)
    except Exception:
        pass


class RunArtifacts:
    def __init__(self, base_dir):
        self.dir = os.path.join(base_dir, time.strftime("%Y-%m-%d_%H%M%S"))
        os.makedirs(os.path.join(self.dir, "cases"), exist_ok=True)
        os.makedirs(os.path.join(self.dir, "posts"), exist_ok=True)

    def write_json(self, name, obj):
        with io.open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, default=str)

    def save_case(self, case):
        p = os.path.join(self.dir, "cases", case["case_id"] + ".json")
        with io.open(p, "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)
        return p

    def save_post(self, case, text, mode):
        p = os.path.join(self.dir, "posts", case["case_id"] + ".txt")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("<!-- mode=%s case_id=%s url=%s -->\n%s" % (mode, case["case_id"],
                                                                 case["source_url"], text))
        return p


def process_candidate(storage, art, url, source, provider, publish, limit_left):
    """Обработка ОДНОГО кандидата. Возвращает dict-итог."""
    out = {"url": url, "source": source, "status": "new", "reason": ""}
    mid = None
    try:
        status_code, html = httpclient.fetch(url)
        mid = storage.add(url, source)
        out["status"] = "fetched"
    except httpclient.FetchError as e:
        out["status"] = "failed"; out["reason"] = "fetch: %s" % e
        return out

    try:
        ext = extraction.extract_from_html(html, url)
        text = ext["text"]
        h = content_hash(text)
        dup = storage.content_duplicated(text, exclude_id=mid)
        if dup or ext["quality"] == "failed":
            storage.update(mid, status="rejected", content_hash=h,
                           reason="duplicate content" if dup else "extraction failed")
            out.update(status="rejected", reason="duplicate" if dup else "extraction failed")
            return out
        if ext["quality"] == "poor":
            storage.update(mid, status="review", content_hash=h,
                           reason="extraction poor (%d chars)" % len(text))
            out.update(status="review", reason="extraction poor")
            return out
        storage.update(mid, status="extracted", content_hash=h)
        out["status"] = "extracted"
    except Exception as e:
        storage.update(mid, status="failed", reason="extract: %s" % e)
        out.update(status="failed", reason="extract: %s" % e)
        return out

    # -------- classification (frozen V2) --------
    try:
        meta = extraction.classifier_meta(ext)
        meta["url"] = url
        cls = V2.classify_v2(text, meta, policy="strict")
    except Exception as e:
        storage.update(mid, status="failed", reason="classify: %s" % e)
        out.update(status="failed", reason="classify: %s" % e)
        return out
    cls_type, conf = cls["type"], cls["confidence"]
    storage.update(mid, status="classified", classification=cls_type,
                   confidence=conf, company=cls["company"])
    out.update(cls_type=cls_type, conf=conf, company=cls["company"])

    review_reason = ""
    if cls_type == "needs_review":
        v = None
        if provider.available:
            raw_v = provider.arbitrate(ext["title"], url, text, cls)
            v, verr = ai.validate_verdict(raw_v, text)
            if verr:
                review_reason = "ai verdict invalid: %s" % verr
            elif v and v.get("decision") in ("business_case", "how_to", "other"):
                # AI Automation: practical guides/workflows/agent reviews allowed through
                # (soft: they go review/post_ready path, not auto-rejected)
                if v.get("decision") == "business_case":
                    cls_type = "business_case"
                    cls["type"] = "business_case"
                else:
                    cls_type = "how_to"  # practical content lane (soft check)
                    cls["type"] = "how_to"
                cls["confidence"] = float(v.get("confidence") or 0.6)
                if v.get("company"):
                    cls["company"] = v["company"]
                out["ai_verdict"] = v.get("decision")
            else:
                review_reason = "ai verdict=%s" % (v or {}).get("decision", "none")
        else:
            review_reason = "review without AI provider"
        out["status"] = "review"; out["reason"] = review_reason
        storage.update(mid, status="review", reason=review_reason[:300])
        return out
    # HARD: only auto-reject clearly non-AI/non-business (spam / off-topic detected by rules);
    # how_to / practical / news go through arbitration above (soft).
    if cls_type not in ("business_case", "how_to"):
        storage.update(mid, status="rejected", reason="rules: %s" % cls_type)
        out.update(status="rejected", reason="rules:%s" % cls_type)
        return out
    # business_case с poor/partial: partial — ок, но бейдж в кейс (см. case_model)

    # -------- CASE + evidence validation --------
    try:
        case = case_model.build_case(url, ext, cls, source=source)
        shape_ok, shape_errors = case_model.validate_case_shape(case)
        ev_ok, ev_errors = evidence.validate_case(case, text)
    except Exception as e:
        storage.update(mid, status="failed", reason="case: %s" % e)
        out.update(status="failed", reason="case: %s" % e)
        return out
    if not (shape_ok and ev_ok):
        reasons = (shape_errors + ev_errors)[:4]
        # неоднозначный материал НЕ публикуем: в review (AI/человек), не reject
        storage.update(mid, status="review",
                       reason="case/evidence: " + " | ".join(reasons)[:400],
                       case_json=json.dumps(case, ensure_ascii=False))
        out.update(status="review", reason="evidence review")
        return out
    storage.set_case(mid, case)
    art.save_case(case)
    out["case_id"] = case["case_id"]

    # -------- post + final validation (hashtags, Russian Language Guard) --------
    post_text, mode, lang_ok = postgen.render_post(case, text, provider=provider)
    tags = postgen.tags_for_case(case)
    if not lang_ok:
        # честная причина: guard или все же редакционный гейт (mode один и тот же)
        eok, eerr = postgen.editorial_check(post_text)
        why = ("editorial: " + "; ".join(eerr)[:150]) if not eok else \
              "language guard: не русский после retry (EN-доминанта)"
        storage.update(mid, status="review", reason=why[:300])
        out.update(status="review", reason="post gate failed")
        return out
    ok, errors = postgen.validate_post(post_text, case, text)
    if not ok:
        storage.update(mid, status="review", reason="post validation: %s" % errors[:2])
        out.update(status="review", reason="post validation failed")
        return out
    art.save_post(case, post_text, mode)
    storage.update(mid, status="post_ready", post_text=post_text)
    out.update(status="post_ready", post_mode=mode, hashtags=tags)

    # -------- publish (race-safe claim) --------
    if publish and limit_left > 0:
        if not storage.claim_for_publish(mid):
            out.update(reason="claim lost (parallel run)")
            return out
        res = telegram.publish_post(post_text, dry_run=False)
        if res.ok:
            storage.mark_published(mid, res.message_id, config.CHAT_ID, case["case_id"],
                                   hashtags=hashtags.render(tags), content_type="case")
            out.update(status="published", telegram_message_id=res.message_id)
        else:
            storage.release_claim(mid, "review", "publish failed: %s" % (res.error or ""))
            out.update(status="review", reason="publish failed: %s" % res.error)
    return out


def run(dry_run=True, limit=None, sources=None, provider=None, storage=None,
        publish=False, log_to_console=True):
    """Один полный цикл. -> итоговый dict (для report/JobContext)."""
    storage = storage or storage_mod.Storage()
    provider = provider or ai.get_provider()
    art = RunArtifacts(config.RUNS_DIR)
    if log_to_console:
        _setup_logging(art.dir)
    log.info("run start dry_run=%s publish=%s provider=%s", dry_run, publish, provider.name)
    if dry_run:
        publish = False
    limit_left = limit if limit is not None else config.PUBLISH_LIMIT

    results = []
    if publish and not dry_run:
        storage.recover_stale_claims()
        # «Новость дня»: отдельный слот, если накопилось >= NEWS_EVERY успешных
        # CASE-публикаций с прошлой новости. Ошибка новости не ломает pipeline.
        if limit_left > 0 and storage.count_cases_since_last_news() >= config.NEWS_EVERY:
            try:
                nrow = news_mod.process_news(storage, art, provider, publish=True)
            except Exception as e:
                nrow = None
                log.warning("news lane failed (isolated): %s", e)
            if nrow:
                results.append(nrow)
                if nrow.get("status") == "published":
                    limit_left -= 1
                log.info("NEWS %s | %s | msg_id=%s", nrow.get("url", ""),
                         nrow.get("status"), nrow.get("telegram_message_id", ""))

    candidates = []
    for src in (sources or config.SOURCES):
        ad = adapters.ADAPTERS.get(src)
        if not ad:
            log.warning("unknown source %s", src)
            continue
        try:
            urls = ad.discover()[: config.MAX_PER_SOURCE * 3]
        except Exception as e:
            log.error("discover %s failed: %s", src, e)
            urls = []
        fresh = []
        for u in urls:
            known = storage.seen_url(u)
            if known and known["status"] in TERMINAL:
                continue
            if known and known.get("status") == "failed" and known.get("attempts", 0) >= 3:
                continue
            fresh.append(u)
        fresh = fresh[: config.MAX_PER_SOURCE]
        candidates.append({"source": src, "total": len(urls), "fresh": fresh})
    art.write_json("candidates.json", candidates)

    for grp in candidates:
        for url in grp["fresh"]:
            if not dry_run and publish and limit_left <= 0:
                break
            row = process_candidate(storage, art, url, grp["source"], provider,
                                    publish, limit_left)
            mid = storage.seen_url(url)
            if mid:
                storage.db.execute("UPDATE materials SET attempts=attempts+1 WHERE id=?",
                                   (mid["id"],))
                storage.db.commit()
            if row.get("status") == "published":
                limit_left -= 1
            results.append(row)
            log.info("RESULT %s | %s | %s | %s", grp["source"], row.get("status"),
                     url, row.get("reason", ""))

    summary = _summarize(results)
    if publish and not dry_run and limit_left > 0:
        # очередь публикации: уже валидированные post_ready материалы из БД
        # (soft dedup по недавним компаниям; hard dedup по case_id/истории;
        #  claim — race safety; news-материалы в case-очередь не попадают)
        for row in _publish_backlog(storage, provider, limit_left):
            results.append(row)
            if row.get("status") == "published":
                limit_left -= 1
        summary = _summarize(results)
    art.write_json("results.json", {"summary": summary, "results": results,
                                    "provider": provider.name, "dry_run": dry_run,
                                    "publish": publish, "ts": now_iso()})
    _write_report(art, candidates, results, summary)
    summary["run_dir"] = art.dir
    return summary


def _publish_backlog(storage, provider, limit_left):
    """Очередь публикации post_ready: приоритет — свежий качественный CASE,
    чья компания/тема давно не публиковалась (soft dedup), затем confidence.
    Hard dedup: case_id уже в publications -> никогда повторно.
    Race safety: атомарный claim перед отправкой."""
    out = []
    rows = [m for m in storage.by_status("post_ready")
            if (m.get("source") or "") != "news"]
    recent = storage.recent_companies()
    published_ids = storage.published_case_ids()

    def prio(m):
        comp = (m.get("company") or "").lower()
        return (1 if comp and comp in recent else 0,)  # recent => в конец (stable)

    rows.sort(key=prio)
    for m in rows:
        if limit_left <= 0:
            break
        text = m.get("post_text") or ""
        try:
            case = json.loads(m.get("case_json") or "{}")
        except Exception:
            case = {}
        cid = case.get("case_id", "")
        row = {"url": m["url"], "source": m.get("source") or "backlog", "case_id": cid}
        if not text:
            storage.update(m["id"], status="review", reason="post_ready without post_text")
            continue
        if cid and cid in published_ids:  # hard dedup по истории
            storage.update(m["id"], status="rejected",
                           reason="duplicate of published case (history)")
            continue
        # нормализация HTML-артефактов/склеек + редакционные гейты по сохранённому тексту
        text, clean_ok = postgen.clean_for_publish(text)
        eok, eerr = postgen.editorial_check(text)
        if not (clean_ok and eok):
            storage.update(m["id"], status="review",
                           reason="editorial check: %s" % "; ".join(eerr)[:200])
            row.update(status="review", reason="editorial check failed")
            out.append(row)
            continue
        # финальный редакционный проход: язык + контролируемые теги
        tags = postgen.tags_for_case(case) if case else hashtags.build(
            "case", text, m.get("company"))
        final, lang_ok, note = langguard.ensure_russian(
            hashtags.apply_to_post(text, tags), provider)
        if not lang_ok:
            storage.update(m["id"], status="review",
                           reason="language guard: %s" % note[:200])
            row.update(status="review", reason="language guard failed")
            out.append(row)
            continue
        final = hashtags.apply_to_post(final, tags)
        if not storage.claim_for_publish(m["id"]):
            continue  # материал уже кем-то захвачен (race) — пропускаем
        res = telegram.publish_post(final, dry_run=False)
        if res.ok:
            storage.mark_published(m["id"], res.message_id, config.CHAT_ID, cid,
                                   hashtags=hashtags.render(tags), content_type="case")
            row.update(status="published", telegram_message_id=res.message_id)
            limit_left -= 1
        else:
            storage.release_claim(m["id"], "review",
                                  "publish failed: %s" % (res.error or ""))
            row.update(status="review", reason="publish failed: %s" % res.error)
        log.info("BACKLOG %s | %s | msg_id=%s", m["url"], row["status"],
                 row.get("telegram_message_id", ""))
        out.append(row)
    return out


def _summarize(results):
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def _write_report(art, candidates, results, summary):
    L = ["# Case pipeline run — %s" % now_iso(), ""]
    L.append("Sources: " + ", ".join("%s(%d fresh/%d found)" %
             (g["source"], len(g["fresh"]), g["total"]) for g in candidates))
    L.append("Summary: " + json.dumps(summary))
    L.append("")
    L.append("| source | status | class | conf | company | case/post | reason |")
    L.append("|---|---|---|---|---|---|---|")
    for r in results:
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r.get("source"), r.get("status"), r.get("cls_type", ""), r.get("conf", ""),
            r.get("company", ""), r.get("case_id") or r.get("post_mode") or "",
            (r.get("reason") or "")[:90]))
    with io.open(os.path.join(art.dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
