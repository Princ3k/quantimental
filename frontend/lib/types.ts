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

/** Today's move, and how it sits against this stock's own daily range. */
export interface SituationMove {
  direction: 'up' | 'down' | 'flat'
  percent: number
  /** True when the move is large relative to this stock's typical daily range. */
  unusual?: boolean
  label?: string
}

/**
 * What is happening to this stock, stated as fact.
 *
 * This is what the product leads with. Every field is checkable against the
 * chart or the headlines on the same screen — nothing here forecasts.
 */
export interface Situation {
  /** One sentence, ready to render. */
  headline: string
  state: 'rising' | 'falling' | 'steady'
  today: SituationMove
  period: SituationMove
  /** Facts worth flagging, most significant first. Empty when nothing is. */
  notable: string[]
  /** Null when sentiment could not be gathered — not the same as zero. */
  attention: { mentions: number; velocity: string; summary: string } | null
}

export interface Headline {
  title: string
  url: string
  /** Publisher name, e.g. "Reuters". Empty when the feed omitted it. */
  source: string
  published_at: string
}

/** What one upstream source returned, and why. */
export interface SourceStatus {
  /** `disabled` means no credentials, which is a choice, not a fault. */
  status: 'ok' | 'empty' | 'disabled' | 'error'
  count: number
  detail: string | null
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
  /** The stories the score was computed from, so a reader can check it. */
  headlines?: Headline[]
  /** Per-source outcome; absent on older responses. */
  sources?: Record<string, SourceStatus> | null
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
  /** What is happening, stated as fact. The product leads with this. */
  situation: Situation
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

// ---------------------------------------------------------------------------
// Signal Desk — market-wide readings, not per-stock
// ---------------------------------------------------------------------------

export type RiskTone = 'risk_on' | 'risk_off' | 'neutral'

export type SignalCategory =
  | 'RATES'
  | 'CREDIT'
  | 'FX'
  | 'COMMODITIES'
  | 'VOL'
  | 'SOCIAL'

export interface MacroSignal {
  category: SignalCategory
  name: string
  /** Plain-English description of the move. */
  text: string
  direction: 'up' | 'down' | 'flat'
  /** Pre-formatted magnitude: "+2.0σ", "+9.4%", or a level. */
  delta: string
  change_percent: number
  /** Standard deviations from this instrument's own normal weekly move. */
  z_score: number
  risk_tone: RiskTone
  /** True when the move clears the threshold for being worth surfacing. */
  notable: boolean
}

export interface SectorReading {
  symbol: string
  name: string
  change_percent: number
  z_score: number
}

export interface SectorSummary {
  available: boolean
  leaders: SectorReading[]
  laggards: SectorReading[]
  /** Percentage of sectors advancing. */
  breadth: number | null
  advancing?: number
  total?: number
}

export interface CompositeContribution {
  name: string
  effect: number
  tone: RiskTone
}

export interface Composite {
  /** 0-100, where 50 is neutral. */
  score: number
  label: string
  tone: RiskTone
  contributions: CompositeContribution[]
}

export interface Narrative {
  text: string
  /** Whether an LLM or the deterministic template produced this. */
  source: 'llm' | 'template' | 'none'
}

export interface SignalDeskUnavailable {
  available: false
  reason: string
  as_of: string
}

export interface SignalDeskData {
  available: true
  as_of: string
  /** Where today's reading sits against recorded history, or null if too little. */
  context?: string | null
  lookback_days: number
  signals: MacroSignal[]
  sectors: SectorSummary
  composite: Composite
  /** Trace for the composite sparkline, oldest first. */
  history: number[]
  narrative?: Narrative
}

export type SignalDeskResponse = SignalDeskData | SignalDeskUnavailable
