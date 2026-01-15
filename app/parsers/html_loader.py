import requests
from bs4 import BeautifulSoup


def load(url: str) -> BeautifulSoup:
    response = requests.get(url, timeout=15)

    # 🔥 принудительно нормализуем кодировку
    response.encoding = response.apparent_encoding

    return BeautifulSoup(response.text, "html.parser")
