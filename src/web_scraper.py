from typing import Optional
import requests
from bs4 import BeautifulSoup  # [web:57][web:60][web:69]


def fetch_and_extract_text(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetches a URL and returns visible text from the <body>.
    Used as a fallback if API content is poor.
    """
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    if not body:
        return None
    # get_text strips tags and returns readable text. [web:57][web:63]
    text = body.get_text(separator=" ", strip=True)
    return text or None
