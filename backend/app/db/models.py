"""
SQLAlchemy database models for Quantimental.

These models represent the core data structure:
- Stocks: The securities we track
- Prices: Historical price/volume data
- Signals: The three-layer intelligence (Quant, Psych, Hybrid)
- Users: Authentication and preferences
- Watchlists: Personalized tracking
- Alerts: User-defined notifications
- News: Scraped news articles
- Sentiment: Raw and aggregated sentiment events
"""

from sqlalchemy import Column, Integer, String, Float, BigInteger, Date, Text, Boolean, ForeignKey, DateTime, Numeric, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()


class Stock(Base):
    """Represents a tradable security."""
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    sector = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    daily_prices = relationship("DailyPrice", back_populates="stock", cascade="all, delete-orphan")
    quant_signals = relationship("QuantSignal", back_populates="stock", cascade="all, delete-orphan")
    psych_signals = relationship("PsychSignal", back_populates="stock", cascade="all, delete-orphan")
    hybrid_signals = relationship("HybridSignal", back_populates="stock", cascade="all, delete-orphan")


class DailyPrice(Base):
    """Historical OHLCV data for each stock."""
    __tablename__ = "daily_prices"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    open = Column(Numeric(10, 2))
    high = Column(Numeric(10, 2))
    low = Column(Numeric(10, 2))
    close = Column(Numeric(10, 2))
    volume = Column(BigInteger)

    # Relationships
    stock = relationship("Stock", back_populates="daily_prices")

    # Composite unique constraint: one price per ticker per date
    __table_args__ = (
        UniqueConstraint('ticker', 'date', name='uq_ticker_date'),
        Index('ix_ticker_date', 'ticker', 'date'),
    )


class QuantSignal(Base):
    """Technical analysis signals from the Quant Engine."""
    __tablename__ = "quant_signals"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False)
    date = Column(Date, nullable=False, index=True)

    # Technical indicators
    rsi = Column(Numeric(5, 2))  # Relative Strength Index (0-100)
    ma_50 = Column(Numeric(10, 2))  # 50-day Moving Average
    ma_200 = Column(Numeric(10, 2))  # 200-day Moving Average

    # Derived signals
    signal = Column(String(50))  # OVERSOLD, OVERBOUGHT, NEUTRAL
    trend_short = Column(String(20))  # BULLISH, BEARISH, NEUTRAL
    trend_long = Column(String(20))  # BULLISH, BEARISH, NEUTRAL

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    stock = relationship("Stock", back_populates="quant_signals")


class PsychSignal(Base):
    """Sentiment analysis signals from the Psych Engine."""
    __tablename__ = "psych_signals"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False)
    date = Column(Date, nullable=False, index=True)

    # Sentiment metrics
    sentiment_score = Column(Numeric(4, 3))  # -1.0 to +1.0
    emotion = Column(String(20))  # FEAR, GREED, FOMO, FUD, NEUTRAL
    hype_velocity = Column(Numeric(5, 2))  # Mentions vs 30-day avg
    mention_count = Column(Integer)
    mention_avg_30d = Column(Integer)

    # Additional context
    top_keywords = Column(Text)  # JSON array of trending keywords

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    stock = relationship("Stock", back_populates="psych_signals")


class HybridSignal(Base):
    """Unified signals from the Hybrid Engine."""
    __tablename__ = "hybrid_signals"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    # Signal output
    signal = Column(String(20), nullable=False, index=True)  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    case_type = Column(String(50))  # "Case 1: Confirmation", "Case 2: Blow-Off Top", "Case 3: Bullish Divergence"
    confidence = Column(Numeric(4, 3), nullable=False, index=True)  # 0.0 to 1.0

    # Explanation
    reason = Column(Text, nullable=False)  # Plain-English explanation
    reason_short = Column(String(255))  # One-liner for feed view

    # Historical context
    historical_accuracy = Column(Numeric(4, 3))  # Win rate for this pattern
    avg_gain_when_correct = Column(Numeric(5, 2))  # Average % gain

    # References to source signals
    quant_signal_id = Column(Integer, ForeignKey("quant_signals.id"))
    psych_signal_id = Column(Integer, ForeignKey("psych_signals.id"))

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    stock = relationship("Stock", back_populates="hybrid_signals")


class User(Base):
    """User accounts and preferences."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Subscription
    subscription_tier = Column(String(20), default="free")  # free, premium, pro

    # Notifications
    notification_token = Column(Text)
    notification_preferences = Column(Text)  # JSON of notification settings

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)

    # Relationships
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")


class Watchlist(Base):
    """User's personalized stock watchlist."""
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    position = Column(Integer, default=0)  # User-defined order

    # Relationships
    user = relationship("User", back_populates="watchlists")


class Alert(Base):
    """User-defined alert conditions."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False)

    # Alert configuration
    condition = Column(String(50), nullable=False)  # SIGNAL_CHANGE, CONFIDENCE_THRESHOLD, etc.
    threshold = Column(Numeric(4, 3))  # For confidence-based alerts

    # State
    is_active = Column(Boolean, default=True)
    last_triggered = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="alerts")


class NewsArticle(Base):
    """Raw news articles scraped from various sources."""
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(512), unique=True, index=True, nullable=False)
    
    # News fields
    title = Column(String(512))
    content = Column(Text)
    summary = Column(Text)
    source_domain = Column(String(100))
    published_at = Column(DateTime, index=True)
    
    # Metadata
    author = Column(String(100))
    image_url = Column(String(512))
    
    # Scraping status
    is_content_available = Column(Boolean, default=False)
    content_fetched_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class SentimentEvent(Base):
    """Individual sentiment events (tweets, reddit posts, news headers)."""
    __tablename__ = "sentiment_events"

    id = Column(BigInteger, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False, index=True)
    
    # Source info
    source = Column(String(50), nullable=False, index=True)  # twitter, reddit, news
    source_id = Column(String(255), index=True)  # External ID
    
    # Content
    text = Column(Text)
    url = Column(String(512))
    author = Column(String(100))
    
    # Sentiment Analysis Results
    sentiment_score = Column(Float)  # -1.0 to 1.0
    sentiment_label = Column(String(20))  # positive, negative, neutral
    confidence = Column(Float)
    
    # Context
    timestamp = Column(DateTime, nullable=False, index=True)  # Event time
    ingested_at = Column(DateTime, default=datetime.utcnow)


class SentimentExplanation(Base):
    """LLM-generated explanations for daily sentiment."""
    __tablename__ = "sentiment_explanations"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("stocks.ticker"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    
    # Content
    explanation = Column(Text, nullable=False)
    key_factors = Column(Text)  # JSON list of key drivers
    
    # Metadata
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Unique constraint: one explanation per ticker per day
    __table_args__ = (
        UniqueConstraint('ticker', 'date', name='uq_explanation_ticker_date'),
    )


class SentimentAggregate(Base):
    """Aggregated sentiment metrics (bucketed by time)."""
    __tablename__ = "sentiment_aggregates"

    ticker = Column(String(10), nullable=False, primary_key=True)
    bucket = Column(DateTime, nullable=False, primary_key=True)
    total_score = Column(Float, default=0.0)
    count = Column(Integer, default=0)

    # Note: In a real TimescaleDB setup, we would convert this to a hypertable.
    # For now, standard PG table with composite PK works for logic.


class CachedRedditPost(Base):
    """Cached Reddit posts for 6-hour batch windows."""
    __tablename__ = "cached_reddit_posts"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), nullable=False, index=True)

    # Post content
    title = Column(String(500), nullable=False)
    url = Column(String(512), nullable=False)
    selftext = Column(Text)

    # Reddit metrics
    score = Column(Integer, default=0)
    num_comments = Column(Integer, default=0)
    author = Column(String(100))
    subreddit = Column(String(50))
    created_utc = Column(Integer)
    permalink = Column(String(512))

    # Sentiment
    sentiment_score = Column(Float, default=0.0)

    # Caching metadata
    batch_timestamp = Column(DateTime, nullable=False, index=True)
    cache_expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('ix_cached_reddit_ticker_batch', 'ticker', 'batch_timestamp'),
    )

class CachedNewsArticle(Base):
    """
    News articles cached in 6-hour batch windows.

    Backs `app/services/ingestion/cache/news_cache_service.py`, which fetches
    trending and per-ticker news at most once per window to stay inside the
    news providers' rate limits.

    `article_type` distinguishes the two caches that share this table:
    'trending' rows are market-wide and have a null ticker, while 'ticker'
    rows belong to one symbol.
    """
    __tablename__ = "cached_news_articles"

    id = Column(Integer, primary_key=True, index=True)

    # 'trending' (market-wide, ticker is NULL) or 'ticker' (symbol-specific)
    article_type = Column(String(20), nullable=False, index=True)
    ticker = Column(String(10), index=True)

    # Article content
    url = Column(String(512), nullable=False)
    title = Column(String(512), nullable=False)
    description = Column(Text)
    source = Column(String(100))
    published_at = Column(DateTime)
    image_url = Column(String(512))
    author = Column(String(100))

    # Caching metadata
    batch_timestamp = Column(DateTime, nullable=False, index=True)
    cache_expires_at = Column(DateTime, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Every read filters on (type, ticker, batch) together.
        Index('ix_cached_news_type_ticker_batch', 'article_type', 'ticker', 'batch_timestamp'),
    )
