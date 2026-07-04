"""Text helpers: URL normalisation, hashing, keyword matching, HTML cleanup."""

import hashlib
import re
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

_TRACKING_PARAMS_PREFIX = ("utm_", "ref", "fbclid", "gclid")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_url(url: str, base: str | None = None) -> str:
    """Resolve relative URLs and strip tracking params / fragments for stable dedup."""
    if base:
        url = urljoin(base, url)
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


def url_hash(url: str) -> str:
    """Stable hash of a normalised URL, used as the dedup key in MongoDB."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def clean_text(value: str | None) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not value:
        return ""
    text = BeautifulSoup(value, "lxml").get_text(separator=" ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def matches_keywords(text: str, keywords: list[str]) -> bool:
    """🔍 Case-insensitive whole-word-ish match of any keyword in the given text."""
    if not keywords:
        return True
    haystack = text.lower()
    for kw in keywords:
        kw = kw.lower().strip()
        if not kw:
            continue
        # Word boundary match to avoid 'eth' matching 'ethereum-unrelated' noise is intentional-loose:
        if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", haystack):
            return True
    return False
