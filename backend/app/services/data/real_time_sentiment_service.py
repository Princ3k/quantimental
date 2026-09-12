"""
Real-time Sentiment Service

Fetches sentiment data from social media/news and analyzes it using ML models.
Provides real psychometric sentiment scores for stock tickers.
"""

import logging
from typing import Dict, Any
from app.services.ingestion.sentiment.sentiment_data_fetcher import fetch_all_sentiment_sources
from app.services.enrichment.sentiment.model import SentimentModel

logger = logging.getLogger(__name__)


class RealTimeSentimentService:
    """
    Service for real-time sentiment analysis using ML models.

    Fetches data from Reddit, Twitter, and News, then analyzes with:
    - FinBERT for news articles
    - Twitter RoBERTa for social media
    - Llama 3 via Groq for discussions
    """

    def __init__(self):
        """Initialize sentiment model."""
        try:
            self.sentiment_model = SentimentModel()
            logger.info("RealTimeSentimentService initialized with ML models")
        except Exception as e:
            logger.error(f"Failed to initialize sentiment models: {e}")
            self.sentiment_model = None

    async def get_sentiment_for_ticker(self, ticker: str) -> Dict[str, Any]:
        """
        Get real-time sentiment analysis for a ticker.

        Args:
            ticker: Stock symbol (e.g., "AAPL", "TSLA")

        Returns:
            Dictionary with sentiment metrics:
                - sentiment_rating: Overall score (0-100)
                - mentions: Total mentions across all sources
                - mention_velocity: "rising", "falling", or "steady"
                - sentiment_score: Normalized sentiment score (0.0-1.0)
                - reddit_buzz: Number of Reddit mentions
                - twitter_buzz: Number of Twitter mentions
                - breakdown: Source-specific sentiment details
        """
        try:
            # Fetch sentiment data from all sources
            logger.info(f"Fetching sentiment data for {ticker}")
            sentiment_data = await fetch_all_sentiment_sources(
                ticker,
                skip_full_text=True  # Fast mode for real-time analysis
            )

            reddit_posts = sentiment_data.get("reddit_posts", [])
            news_articles = sentiment_data.get("marketaux_news", [])
            tweets = sentiment_data.get("twitter_posts", [])

            # Analyze sentiment if model is available, otherwise use fallback
            if self.sentiment_model:
                reddit_sentiment = self._analyze_reddit_with_ml(reddit_posts)
                news_sentiment = self._analyze_news_with_ml(news_articles)
                twitter_sentiment = self._analyze_twitter_with_ml(tweets)
            else:
                # Fallback to simple aggregation
                reddit_sentiment = self._simple_reddit_analysis(reddit_posts)
                news_sentiment = self._simple_news_analysis(news_articles)
                twitter_sentiment = self._simple_twitter_analysis(tweets)

            # Aggregate sentiment from all sources
            aggregated = self._aggregate_sentiment(
                reddit_sentiment, news_sentiment, twitter_sentiment
            )

            return aggregated

        except Exception as e:
            logger.error(f"Error getting sentiment for {ticker}: {e}")
            # Return neutral sentiment on error
            return {
                "sentiment_rating": 50,
                "mentions": 0,
                "mention_velocity": "steady",
                "sentiment_score": 0.5,
                "reddit_buzz": 0,
                "twitter_buzz": 0,
                "breakdown": {
                    "reddit": {"score": 50, "mentions": 0},
                    "news": {"score": 50, "mentions": 0},
                    "twitter": {"score": 50, "mentions": 0}
                }
            }

    def _analyze_reddit_with_ml(self, posts: list) -> Dict[str, Any]:
        """Analyze Reddit posts using Llama 3 via Groq."""
        if not posts:
            return {"score": 50, "mentions": 0, "sentiment": 0.0}

        sentiments = []
        for post in posts[:20]:  # Analyze top 20 posts
            text = f"{post.get('title', '')} {post.get('text', '')}"
            if text.strip():
                try:
                    result = self.sentiment_model.analyze(text, source_type="discussion")
                    # Convert sentiment to score
                    sent = result.get("sentiment", "neutral").lower()
                    if sent in ["bullish", "positive"]:
                        sentiments.append(0.7)
                    elif sent in ["bearish", "negative"]:
                        sentiments.append(0.3)
                    else:
                        sentiments.append(0.5)
                except Exception as e:
                    logger.warning(f"Error analyzing Reddit post: {e}")
                    sentiments.append(0.5)

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.5
        score = int(avg_sentiment * 100)

        return {
            "score": score,
            "mentions": len(posts),
            "sentiment": avg_sentiment
        }

    def _analyze_news_with_ml(self, articles: list) -> Dict[str, Any]:
        """Analyze news articles using FinBERT."""
        if not articles:
            return {"score": 50, "mentions": 0, "sentiment": 0.0}

        sentiments = []
        for article in articles[:15]:  # Analyze top 15 articles
            text = f"{article.get('title', '')} {article.get('description', '')}"
            if text.strip():
                try:
                    result = self.sentiment_model.analyze(text, source_type="news")
                    # FinBERT returns "positive", "negative", "neutral"
                    sent = result.get("sentiment", "neutral").lower()
                    if sent == "positive":
                        sentiments.append(0.7)
                    elif sent == "negative":
                        sentiments.append(0.3)
                    else:
                        sentiments.append(0.5)
                except Exception as e:
                    logger.warning(f"Error analyzing news article: {e}")
                    sentiments.append(0.5)

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.5
        score = int(avg_sentiment * 100)

        return {
            "score": score,
            "mentions": len(articles),
            "sentiment": avg_sentiment
        }

    def _analyze_twitter_with_ml(self, tweets: list) -> Dict[str, Any]:
        """Analyze tweets using Twitter RoBERTa."""
        if not tweets:
            return {"score": 50, "mentions": 0, "sentiment": 0.0}

        sentiments = []
        for tweet in tweets[:25]:  # Analyze top 25 tweets
            text = tweet.get('text', '')
            if text.strip():
                try:
                    result = self.sentiment_model.analyze(text, source_type="social")
                    # Twitter RoBERTa returns "bullish", "bearish", "neutral"
                    sent = result.get("sentiment", "neutral").lower()
                    if sent == "bullish":
                        sentiments.append(0.7)
                    elif sent == "bearish":
                        sentiments.append(0.3)
                    else:
                        sentiments.append(0.5)
                except Exception as e:
                    logger.warning(f"Error analyzing tweet: {e}")
                    sentiments.append(0.5)

        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.5
        score = int(avg_sentiment * 100)

        return {
            "score": score,
            "mentions": len(tweets),
            "sentiment": avg_sentiment
        }

    def _simple_reddit_analysis(self, posts: list) -> Dict[str, Any]:
        """Fallback Reddit analysis without ML."""
        return {"score": 50, "mentions": len(posts), "sentiment": 0.5}

    def _simple_news_analysis(self, articles: list) -> Dict[str, Any]:
        """Fallback news analysis without ML."""
        # Use MarketAux sentiment if available
        if articles:
            avg_sent = sum(a.get('sentiment_score', 0) for a in articles) / len(articles)
            score = int((avg_sent + 1) * 50)  # Convert from -1/1 to 0/100
            return {"score": score, "mentions": len(articles), "sentiment": (avg_sent + 1) / 2}
        return {"score": 50, "mentions": 0, "sentiment": 0.5}

    def _simple_twitter_analysis(self, tweets: list) -> Dict[str, Any]:
        """Fallback Twitter analysis without ML."""
        return {"score": 50, "mentions": len(tweets), "sentiment": 0.5}

    def _aggregate_sentiment(
        self, reddit_data: Dict, news_data: Dict, twitter_data: Dict
    ) -> Dict[str, Any]:
        """
        Aggregate sentiment from all sources.

        Weights:
        - News: 50% (most reliable)
        - Reddit: 30% (retail sentiment)
        - Twitter: 20% (real-time buzz)
        """
        reddit_score = reddit_data.get('score', 50)
        news_score = news_data.get('score', 50)
        twitter_score = twitter_data.get('score', 50)

        # Weighted average
        unified_score = int(
            (news_score * 0.50) +
            (reddit_score * 0.30) +
            (twitter_score * 0.20)
        )

        total_mentions = (
            reddit_data.get('mentions', 0) +
            news_data.get('mentions', 0) +
            twitter_data.get('mentions', 0)
        )

        # Determine velocity
        if total_mentions > 50:
            velocity = "rising"
        elif total_mentions < 10:
            velocity = "falling"
        else:
            velocity = "steady"

        return {
            "sentiment_rating": unified_score,
            "mentions": total_mentions,
            "mention_velocity": velocity,
            "sentiment_score": unified_score / 100,
            "reddit_buzz": reddit_data.get('mentions', 0),
            "twitter_buzz": twitter_data.get('mentions', 0),
            "breakdown": {
                "reddit": reddit_data,
                "news": news_data,
                "twitter": twitter_data
            }
        }
