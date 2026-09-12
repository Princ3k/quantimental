#!/usr/bin/env python3
"""
Create the cached_reddit_posts table for 6-hour Reddit post caching.
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
from app.db.models import CachedRedditPost

def create_cached_reddit_table():
    """Create the cached_reddit_posts table."""
    print("Creating cached_reddit_posts table...")

    try:
        # Create only the CachedRedditPost table using sync engine
        CachedRedditPost.__table__.create(engine, checkfirst=True)

        print("✅ Table created successfully!")
        print("\nTable schema:")
        print("- ticker: Stock ticker (indexed)")
        print("- title, url, selftext, score, num_comments, author, subreddit")
        print("- created_utc, permalink")
        print("- sentiment_score: Calculated sentiment (-1.0 to +1.0)")
        print("- batch_timestamp: When this batch was fetched (6-hour window)")
        print("- cache_expires_at: When to refresh (6 hours from batch_timestamp)")
        print("\nIndexes:")
        print("- (ticker, batch_timestamp)")
        print("- cache_expires_at")

    except Exception as e:
        print(f"❌ Error creating table: {e}")
        raise
    finally:
        engine.dispose()

if __name__ == "__main__":
    create_cached_reddit_table()