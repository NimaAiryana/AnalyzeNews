"""Registry mapping each SourceSite to its crawler class.

To add a new site: implement a BaseCrawler subclass and register it here.
"""

from app.crawlers.base import BaseCrawler
from app.crawlers.crypto_news import CryptoNewsCrawler
from app.crawlers.cryptonews import CryptoNewsComCrawler
from app.crawlers.cryptopanic import CryptoPanicCrawler
from app.models.enums import SourceSite

CRAWLER_REGISTRY: dict[SourceSite, type[BaseCrawler]] = {
    SourceSite.CRYPTOPANIC: CryptoPanicCrawler,
    SourceSite.CRYPTO_NEWS: CryptoNewsCrawler,
    SourceSite.CRYPTONEWS: CryptoNewsComCrawler,
}


def all_sites() -> list[SourceSite]:
    return list(CRAWLER_REGISTRY.keys())
