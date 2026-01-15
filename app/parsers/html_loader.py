import requests
from bs4 import BeautifulSoup


def load(url: str) -> BeautifulSoup:
    r = requests.get(url, timeout=15)
    r.encoding = r.apparent_encoding
    return BeautifulSoup(r.text, "html.parser")
