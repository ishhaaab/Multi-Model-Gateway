"""Web search + page fetching, shared by the web_search/fetch_page tools
and the deep-research orchestrator.

Search uses a self hosted SearXNG instance when SEARXNG_URL is set,
otherwise DuckDuckGo's HTML endpoint cus no API key needed :).
"""
import asyncio
import html as html_lib
import ipaddress
import logging
import re
import socket
from urllib.parse import parse_qs, urlsplit

import httpx

from app.core.config import settings
from app.core.metrics import search_degraded_total

logger = logging.getLogger(__name__)

# Hard cap on redirect hops we'll follow (each one is re-validated for SSRF).
_MAX_REDIRECTS = 5


class UnsafeURLError(Exception):
    """Raised when a fetch target resolves to a non-public address (SSRF guard)."""


async def _assert_public_host(host: str) -> None:
    """Resolve `host` and refuse if ANY resolved address is private, loopback,
    link-local, reserved, multicast, or the cloud-metadata IP. Runs before every
    connection (initial URL and each redirect hop) so a public host can't redirect
    into the internal network. DNS resolution is offloaded so it can't block the loop."""
    if not host:
        raise UnsafeURLError("missing host")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"could not resolve host '{host}'") from e
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local      # covers 169.254.0.0/16 incl. cloud metadata
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"refusing to fetch non-public address {addr} (host '{host}')")

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style|noscript|svg|head)\b.*?</\1>", re.S | re.I)
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")
_DDG_TITLE_RE = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_DDG_SNIPPET_RE = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.S)

_USER_AGENT = "Mozilla/5.0 (compatible; llm-gateway/1.0)"


def _clean(fragment: str) -> str:
    return html_lib.unescape(_TAG_RE.sub("", fragment)).strip()


def _resolve_ddg_url(href: str) -> str:
    # result links are redirects of the form //duckduckgo.com/l/?uddg=<urlencoded target>
    if "uddg=" in href:
        target = parse_qs(urlsplit(href).query).get("uddg", [""])[0]
        if target:
            return target
    return href


async def _searxng(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{settings.SEARXNG_URL.rstrip('/')}/search",
            params={"q": query, "format": "json"},
        )
        response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        # a 200 with zero hits is a degraded search, not a success (R6)
        logger.warning("SearXNG returned zero results for query '%s'", query)
        search_degraded_total.labels(source="searxng").inc()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in results[:limit]
    ]


async def _duckduckgo(query: str, limit: int) -> list[dict]:
    async with httpx.AsyncClient(
        timeout=15, headers={"User-Agent": _USER_AGENT}, follow_redirects=True,
    ) as client:
        response = await client.post("https://html.duckduckgo.com/html/", data={"q": query})
        response.raise_for_status()

    page = response.text
    titles = _DDG_TITLE_RE.findall(page)
    if not titles:
        # 200 with no result links: DDG quietly degraded (rate-limited page,
        # bot wall, or genuinely nothing) — surface it instead of returning []
        logger.warning("DuckDuckGo returned zero results for query '%s'", query)
        search_degraded_total.labels(source="duckduckgo").inc()
    snippets = [_clean(s) for s in _DDG_SNIPPET_RE.findall(page)]
    return [
        {
            "title": _clean(title),
            "url": _resolve_ddg_url(href),
            "snippet": snippets[i] if i < len(snippets) else "",
        }
        for i, (href, title) in enumerate(titles[:limit])
    ]


async def search(query: str, limit: int | None = None) -> list[dict]:
    """Top web results as [{title, url, snippet}]."""
    limit = limit or settings.WEB_SEARCH_MAX_RESULTS
    if settings.SEARXNG_URL:
        return await _searxng(query, limit)
    return await _duckduckgo(query, limit)


async def fetch_page(url: str, max_chars: int | None = None) -> str:
    """Fetch a URL and return its visible text (tags stripped, whitespace
    collapsed), truncated to max_chars."""
    max_chars = max_chars or settings.RESEARCH_PAGE_MAX_CHARS
    # follow_redirects=False so we re-validate every hop ourselves — auto-follow
    # and SSRF protection are mutually exclusive (a public URL can 302 to an internal one).
    async with httpx.AsyncClient(
        timeout=20, headers={"User-Agent": _USER_AGENT}, follow_redirects=False,
    ) as client:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            parsed = urlsplit(current)
            if parsed.scheme not in ("http", "https"):
                raise UnsafeURLError(f"unsupported scheme '{parsed.scheme}'")
            await _assert_public_host(parsed.hostname or "")
            response = await client.get(current)
            if response.is_redirect and response.next_request is not None:
                current = str(response.next_request.url)  # httpx resolves relative Location
                continue
            break
        else:
            raise UnsafeURLError("too many redirects")
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        return f"(unsupported content type: {content_type})"

    text = _SCRIPT_RE.sub(" ", response.text)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", "\n".join(line.strip() for line in text.splitlines())).strip()

    if len(text) > max_chars:
        text = text[:max_chars] + "\n[truncated]"
    return text
