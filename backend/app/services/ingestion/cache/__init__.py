"""
Cache Services Package

Caches API responses to stay inside upstream rate limits.

    from app.services.ingestion.cache.reddit_cache_service import get_reddit_posts_with_cache

`news_cache_service` used to live here and was removed: it cached NewsAPI,
which this project no longer uses; it imported two functions that had since
been deleted, so the module could not even be loaded; and every function took
a database session, which production does not have. Three independent reasons
it could never have run, and it sat here long enough to be mistaken for
protection that existed. In-process caching for the live sources lives in
`sentiment/sentiment_data_fetcher.py` instead.
"""
