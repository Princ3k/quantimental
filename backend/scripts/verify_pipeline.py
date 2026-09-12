#!/usr/bin/env python3
"""
End-to-End Pipeline Test

Tests the complete sentiment analysis pipeline:
Producer -> Kafka -> Classifier -> Kafka -> Aggregator -> DB
"""

import asyncio
import time
from app.db.session import async_session
from sqlalchemy import select, text as sql_text

async def check_db():
    """Check database for results."""
    async with async_session() as session:
        # Check sentiment_events
        result = await session.execute(sql_text("SELECT COUNT(*) FROM sentiment_events"))
        events_count = result.scalar()
        
        # Check sentiment_aggregates
        result = await session.execute(sql_text("SELECT COUNT(*) FROM sentiment_aggregates"))
        agg_count = result.scalar()
        
        print(f"\n📊 Database Results:")
        print(f"   sentiment_events: {events_count}")
        print(f"   sentiment_aggregates: {agg_count}")
        
        if events_count > 0:
            # Show sample
            result = await session.execute(
                sql_text("SELECT ticker, sentiment_score, sentiment_label FROM sentiment_events LIMIT 3")
            )
            rows = result.fetchall()
            print(f"\n   Sample events:")
            for row in rows:
                print(f"   - {row[0]}: {row[2]} ({row[1]:.2f})")
        
        if agg_count > 0:
            result = await session.execute(
                sql_text("SELECT ticker, bucket, total_score, count FROM sentiment_aggregates LIMIT 3")
            )
            rows = result.fetchall()
            print(f"\n   Sample aggregates:")
            for row in rows:
                print(f"   - {row[0]} @ {row[1]}: avg={row[2]/row[3]:.2f} (n={row[3]})")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔍 E2E Pipeline Verification")
    print("="*60)
    print("\nChecking database state...")
    asyncio.run(check_db())
    print("\n" + "="*60)

