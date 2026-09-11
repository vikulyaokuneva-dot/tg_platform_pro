# -*- coding: utf-8 -*-
"""case_pipeline.httpclient — вежливый HTTP с retry/timeout/UA и логом без секретов.

Кэширование: in-process dict по URL (одна страница не скачивается дважды за прогон).
"""
import time

import requests

from . import config

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8,ru;q=0.7",
}

_cache = {}
_last_hit = {}


class FetchError(Exception):
    def __init__(self, url, status=None, reason=""):
        super().__init__(("%s %s %s" % (url, status or "", reason)).strip())
        self.url = url
        self.status = status
        self.reason = reason


def fetch(url, polite=True, timeout=None, use_cache=True):
    """GET c ретраями; возвращает (status_code, text). Честный Fail: FetchError."""
    key = url
    if use_cache and key in _cache:
        return _cache[key]
    timeout = timeout or config.FETCH_TIMEOUT_SEC
    if polite:
        dom = key.split("/")[2] if "//" in key else ""
        wait = config.POLITE_DELAY_SEC - (time.time() - _last_hit.get(dom, 0))
        if wait > 0:
            time.sleep(wait)
    last = None
    for attempt in range(config.FETCH_RETRIES + 1):
        try:
            r = requests.get(key, headers=UA, timeout=timeout, allow_redirects=True)
            _last_hit[key.split("/")[2]] = time.time()
            if r.status_code == 200:
                out = (r.status_code, r.text)
                if use_cache:
                    _cache[key] = out
                return out
            if r.status_code in (403, 404, 410):
                raise FetchError(key, status=r.status_code, reason="permanent")
            last = FetchError(key, status=r.status_code, reason="retryable")
        except FetchError:
            raise
        except Exception as e:
            last = FetchError(key, reason=type(e).__name__)
        time.sleep(1.5 * (attempt + 1))
    raise last or FetchError(key, reason="unknown")
