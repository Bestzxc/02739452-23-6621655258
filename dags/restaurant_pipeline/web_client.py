"""HTTP helper ที่เคารพ robots.txt และ Crawl-delay"""

import logging
import time
from urllib import robotparser
from urllib.parse import urlparse

import requests

from restaurant_pipeline.config import DEFAULT_DELAY_SEC, HTTP_TIMEOUT_SEC, USER_AGENT

log = logging.getLogger(__name__)

_robots_cache: dict[str, robotparser.RobotFileParser] = {}
_last_request_at: dict[str, float] = {}


class RobotsDisallowed(Exception):
    pass


def _robots_for(url: str) -> robotparser.RobotFileParser:
    parts = urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots_cache:
        # ใช้ requests + User-Agent ของโปรเจกต์แทน rp.read() — บางเว็บตอบ 403 ให้ UA ของ urllib
        # ซึ่ง robotparser จะตีความว่า "ห้ามทุกหน้า"
        rp = robotparser.RobotFileParser(f"{host}/robots.txt")
        resp = requests.get(f"{host}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_SEC)
        if resp.status_code in (401, 403):
            rp.disallow_all = True
        elif resp.status_code >= 400:
            rp.allow_all = True
        else:
            rp.parse(resp.text.splitlines())
        _robots_cache[host] = rp
    return _robots_cache[host]


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "th,en;q=0.8"})
    return s


def polite_get(s: requests.Session, url: str) -> requests.Response:
    """GET แบบสุภาพ: เช็ก robots.txt ก่อน และเว้นระยะตาม Crawl-delay ต่อโดเมน"""
    rp = _robots_for(url)
    if not rp.can_fetch(USER_AGENT, url):
        raise RobotsDisallowed(f"robots.txt ไม่อนุญาต: {url}")

    host = urlparse(url).netloc
    delay = rp.crawl_delay(USER_AGENT) or DEFAULT_DELAY_SEC
    wait = _last_request_at.get(host, 0) + delay - time.monotonic()
    if wait > 0:
        time.sleep(wait)

    log.info("GET %s", url)
    resp = s.get(url, timeout=HTTP_TIMEOUT_SEC)
    _last_request_at[host] = time.monotonic()
    resp.raise_for_status()
    return resp
