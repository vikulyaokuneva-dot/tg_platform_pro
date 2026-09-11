# -*- coding: utf-8 -*-
"""case_pipeline.utils — нормализации и мелкие хелперы."""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

UTM_RX = re.compile(r"(utm_|ga_|fbclid|gclid|mc_)", re.I)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_url(url):
    """Канонический URL для дедупа: схема+хост(без www)+путь, query/фрагменты
    со tracking-параметрами и без них отбрасываются, хвостовой слэш убирается."""
    if not url:
        return ""
    s = urlsplit(url.strip().lower())
    host = s.netloc
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", s.path).rstrip("/")
    keep_q = ""
    if s.query and not UTM_RX.search(s.query) and len(s.query) < 40:
        keep_q = s.query  # не tracking — сохраняем (например, ?page=2)
    return urlunsplit((s.scheme, host, path, keep_q, ""))


def domain(url):
    try:
        h = urlsplit(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def content_hash(text):
    t = re.sub(r"\s+", " ", (text or "")).strip().lower()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def ws_norm(text):
    """Нормализация для сверки цитат: юникод-кавычки/тире/nbsp -> ascii, whitespace
    схлопнут, регистр нижний."""
    t = (text or "").replace("\u2019", "'").replace("\u2018", "'") \
        .replace("\u201c", '"').replace("\u201d", '"') \
        .replace("\u00ab", '"').replace("\u00bb", '"') \
        .replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ") \
        .replace("\u2011", "-").replace("\u2010", "-").replace("\u2212", "-") \
        .replace("\u2012", "-").replace("\u2013", "-").replace("\u2015", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


NUM_RX = re.compile(r"[-+]?\d[\d.,]*\s*(?:%|п\.п\.|K|M|B|млн|млрд|тыс|x|раз|₽|\$|USD|EUR|\bhrs?\b|\bhours?\b)?",
                    re.I)


def norm_num_text(text):
    """Склейка разделителей тысяч: '1 000'/'1 000' -> '1000', чтобы перевод
    EN '2,000' -> RU '2 000' не считался новым числом."""
    return re.sub(r"(?<=\d)[\s\u00a0]+(?=\d{3}(\D|$))", "", text or "")


def digits_of(token):
    return re.sub(r"\D", "", token or "")


def extract_numbers(text):
    """Множество числовых токенов (нормализованных) для evidence-валидации цифр."""
    out = set()
    for m in NUM_RX.finditer(text or ""):
        tok = re.sub(r"\s+", "", m.group(0)).strip(".,+-").lower()
        if tok and any(c.isdigit() for c in tok):
            out.add(tok)
    return out
