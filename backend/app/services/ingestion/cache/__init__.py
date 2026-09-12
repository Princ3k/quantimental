"""
Cache Services Package

Services for caching API responses (news, Reddit) to minimize rate limiting.
"""

# Note: These services require database models to be available.
# Import from submodules directly:
#   from app.services.ingestion.cache.news_cache_service import get_news_with_cache
#   from app.services.ingestion.cache.reddit_cache_service import get_reddit_posts_with_cache
