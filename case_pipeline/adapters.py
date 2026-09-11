# -*- coding: utf-8 -*-
"""case_pipeline.adapters — адаптеры источников.

Адаптер отвечает ТОЛЬКО за: discovery (список свежих URL из каталога источника)
и нормализацию URL. Fetch/extract/classify — общие этапы пайплайна.
Новый источник = подкласс + регистрация в ADAPTERS, ядро не трогается.
"""
import logging
import re

from .httpclient import fetch, FetchError

log = logging.getLogger("case_pipeline.adapters")


class SourceAdapter:
    name = "base"
    catalog = ""
    url_rx = None          # абсолютные URL из href/текста страницы
    href_rx = None         # относительные slug-паттерны (строится полный URL)
    base = ""

    def discover(self):
        """-> list[str] candidate article URLs в порядке появления на каталоге."""
        urls, seen = [], set()
        for page in self.catalogs():
            try:
                _, html = fetch(page, timeout=45)
            except FetchError as e:
                log.warning("discover %s failed: %s", self.name, e)
                continue
            found = []
            if self.url_rx:
                found += [m.group(0) for m in re.finditer(self.url_rx, html)]
            if self.href_rx:
                found += [self.base + m.group(1) for m in re.finditer(self.href_rx, html)]
            for u in found:
                u = re.sub(r"[?#].*$", "", u).rstrip("/") + ("/" if self.trailing_slash else "")
                u = re.sub(r"https?://(www\.)?", "https://", u)
                if u not in seen and self.accept(u):
                    seen.add(u)
                    found_ok = True
                    urls.append(u)
        return urls

    catalogs = lambda self: [self.catalog]
    trailing_slash = False

    def accept(self, url):
        slug = url.rstrip("/").rsplit("/", 1)[-1].lower()
        bad = ("page", "rss", "feed", "sitemap", "login", "signup", "undefined",
               "tag", "author", "category", "search")
        return slug and slug not in bad and not slug.isdigit() and len(slug) > 2


class MindboxAdapter(SourceAdapter):
    name = "mindbox"
    catalog = "https://mindbox.ru/journal/cases/"
    url_rx = r"https://mindbox\.ru/journal/cases/[a-z0-9\-]+/?\b"
    trailing_slash = True

    def accept(self, url):
        return url.rstrip("/") not in ("https://mindbox.ru/journal/cases",) and "/cases/" in url


class IBMAdapter(SourceAdapter):
    name = "ibm"
    catalogs_list = ("https://www.ibm.com/case-studies/1/", "https://www.ibm.com/case-studies/2/")
    url_rx = r"https://www\.ibm\.com/case-studies/[a-z0-9\-]+\b"

    def catalogs(self):
        return list(self.catalogs_list)

    def accept(self, url):
        return url.rstrip("/") != "https://www.ibm.com/case-studies" \
            and not re.search(r"/case-studies/\d+$", url)


class ZapierAdapter(SourceAdapter):
    name = "zapier"
    catalog = "https://zapier.com/customer-stories"
    href_rx = r'href="/customer-stories/([a-z0-9\-]+)"'
    base = "https://zapier.com/customer-stories/"


class SalesforceAdapter(SourceAdapter):
    name = "salesforce"
    catalog = "https://www.salesforce.com/customer-stories/"
    url_rx = r"https://www\.salesforce\.com/customer-stories/[a-z0-9\-]+/"
    trailing_slash = True

    def accept(self, url):
        return "/customer-stories/" in url and not re.search(r"/page/\d+", url) \
            and url.rstrip("/") != "https://www.salesforce.com/customer-stories"


# Bitrix24 journal: по holdout-валидации это HOW-TO источник, а не клиентские
# кейсы — в production-пайплайн кейсов не включён (см. README, решение
# задокументировано). Адаптер-заготовка:
class Bitrix24HowToAdapter(MindboxAdapter):
    name = "bitrix24_journal"
    catalog = "https://www.bitrix24.ru/journal/"
    url_rx = r"https://www\.bitrix24\.ru/journal/[a-z0-9\-]+/"
    trailing_slash = True


ADAPTERS = {a.name: a() for a in (MindboxAdapter, IBMAdapter, ZapierAdapter, SalesforceAdapter)}
