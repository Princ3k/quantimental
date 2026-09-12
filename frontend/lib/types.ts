/**
 * Types mirroring the backend's JSON contract.
 *
 * Kept in one file so a backend change surfaces as a type error in exactly one
 * place. Anything the backend can legitimately omit is typed as nullable here
 * rather than being optimistically non-null — the whole point of the rewrite
 * was that missing data is reported honestly instead of being filled in.
 */

export type SignalDirection = 'bullish' | 'bearish' | 'neutral'

export type RecommendationAction =
  | 'strong_buy'
  | 'buy'
  | 'hold'
  | 'sell'
  | 'strong_sell'

export type TrendLabel =
  | 'strong_uptrend'
  | 'uptrend'
  | 'sideways'
  | 'downtrend'
  | 'strong_downtrend'

export type Volatility = 'high' | 'moderate' | 'low'

export type MentionVelocity = 'rising' | 'falling' | 'steady' | 'unknown'

export interface Pattern {
  id: string
  name: string
  description: string
}

export interface Recommendation {
  action: RecommendationAction
  label: string
  /** 0-95. Derived from evidence, never random. */
  confidence: number
  /** One jargon-free sentence explaining the call. */
  summary: string
  reasons: string[]
  pattern: Pattern | null
}

/** Pre-worded momentum reading. The backend owns these bands. */
export interface MomentumReading {
  value: number
  label: string
  meaning: string
}

export interface TechnicalAnalysis {
  trend: TrendLabel
  rsi: number
  momentum: MomentumReading
  volatility: Volatility
  macd: number
  macd_signal: number
  macd_histogram: number
  stochastic_k: number
  adx: number
  bollinger_upper: number
  bollinger_lower: number
  sma_20: number
  sma_50: number
  /** Null when there is less than 200 sessions of history. */
  sma_200: number | null
  golden_cross: boolean
  death_cross: boolean
  avg_volume: number
  price_change_10d: number
  notes: string[]
}

export interface SentimentAnalysis {
  /** False when sentiment could not be gathered. Check before reading `rating`. */
  available: boolean
  /** Null whenever `available` is false — never a fabricated neutral 50. */
  rating: number | null
  mentions: number
  mention_velocity: MentionVelocity
  reddit_buzz: number
  twitter_buzz: number
  /** Explains why sentiment is missing, when it is. */
  reason: string | null
}

export interface DataQuality {
  bars: number
  sufficient: boolean
  has_sma_200: boolean
  has_intraday_range: boolean
}

export interface SignalMetadata {
  analyzed_at: string
  depth: 'fast' | 'full'
  data_sources: string[]
  data_quality: DataQuality
}

export interface StockSignal {
  ticker: string
  available: true
  company_name: string
  sector: string | null
  price: number
  change: number
  change_percent: number
  /** Recent closes, oldest first. Powers the sparkline. */
  price_history: number[]
  signal: SignalDirection
  hybrid_score: number
  technical_rating: number
  /** Null when sentiment was unavailable. */
  sentiment_rating: number | null
  recommendation: Recommendation
  technical_analysis: TechnicalAnalysis
  sentiment_analysis: SentimentAnalysis
  weights: { technical: number; sentiment: number }
  metadata: SignalMetadata
}

export interface SignalFailure {
  ticker: string
  reason: string
}

export interface BatchResponse {
  signals: StockSignal[]
  failed: SignalFailure[]
  success: boolean
  total_processed: number
  processing_time_ms: number
}

export interface AnalyzeResponse {
  signal: StockSignal | null
  success: boolean
  error: string | null
  processing_time_ms: number
}

export interface SearchResult {
  ticker: string
  name: string
  exchange: string | null
  type: string | null
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
}

export interface NewsArticle {
  id: number
  url: string
  title: string
  source: string
  published_at: string | null
  image_url: string | null
  summary: string | null
  sentiment: { score: number | null; label: string | null; confidence: number | null }
  impact: { sentiment: SignalDirection; impact: 'high' | 'medium' | 'low'; score: number }
  has_content: boolean
}

export interface TickerNewsResponse {
  ticker: string
  articles: NewsArticle[]
  count: number
  available: boolean
  reason?: string
}
