#!/usr/bin/env python3
"""
Create the cached_news_articles table for 6-hour NewsAPI caching.
Run this once to add the table to your database.
"""

from pathlib import Path
from dotenv import load_dotenv

# Force load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)
else:
    print(f"WARNING: .env file not found at {ENV_PATH}")

from app.db.session import engine
from app.db.models import CachedNewsArticle

def create_cached_news_table():
    """Create the cached_news_articles table."""
    print("Creating cached_news_articles table...")

    try:
        # Create only the CachedNewsArticle table using sync engine
        CachedNewsArticle.__table__.create(engine, checkfirst=True)

        print("✅ Table created successfully!")
        print("\nTable schema:")
        print("- article_type: 'trending' or 'ticker'")
        print("- ticker: Stock ticker (null for trending articles)")
        print("- url, title, description, source, published_at, image_url, author")
        print("- batch_timestamp: When this batch was fetched")
        print("- cache_expires_at: When to refresh (6 hours from batch_timestamp)")

    except Exception as e:
        print(f"❌ Error creating table: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    create_cached_news_table()