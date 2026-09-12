/**
 * Presentation helpers: turning backend values into language a first-time
 * investor can act on.
 *
 * Everything user-facing that involves a judgement call about wording lives
 * here rather than being scattered through components, so the vocabulary stays
 * consistent across the app.
 *
 * The house rule: **no bare jargon on screen.** A term like RSI or ADX may
 * appear only alongside its plain-English meaning. Where the underlying value
 * is still useful, it is renamed to something self-explanatory ("momentum",
 * "trend strength") and the technical name is offered as a footnote.
 */

import type {
  MentionVelocity,
  RecommendationAction,
  TrendLabel,
  Volatility,
} from './types'

/** Semantic tone used to pick colours. Never colour alone — always with text. */
export type Tone = 'positive' | 'mild-positive' | 'neutral' | 'mild-negative' | 'negative'

export const ACTION_TONE: Record<RecommendationAction, Tone> = {
  strong_buy: 'positive',
  buy: 'mild-positive',
  hold: 'neutral',
  sell: 'mild-negative',
  strong_sell: 'negative',
}

/**
 * What each recommendation actually means, in the second person.
 *
 * Deliberately hedged: these describe what the signals show, not what the
 * reader should do with their money.
 */
export const ACTION_MEANING: Record<RecommendationAction, string> = {
  strong_buy: 'The price trend and market mood are both clearly positive.',
  buy: 'The overall picture leans positive, with some caveats.',
  hold: 'The signals are mixed or quiet. There is no clear edge either way today.',
  sell: 'The overall picture leans negative, with some caveats.',
  strong_sell: 'The price trend and market mood are both clearly negative.',
}

export const TREND_LABEL: Record<TrendLabel, string> = {
  strong_uptrend: 'Rising steadily',
  uptrend: 'Drifting up',
  sideways: 'Going nowhere',
  downtrend: 'Drifting down',
  strong_downtrend: 'Falling steadily',
}

export const TREND_TONE: Record<TrendLabel, Tone> = {
  strong_uptrend: 'positive',
  uptrend: 'mild-positive',
  sideways: 'neutral',
  downtrend: 'mild-negative',
  strong_downtrend: 'negative',
}

export const VOLATILITY_LABEL: Record<Volatility, string> = {
  high: 'Bumpy',
  moderate: 'Normal',
  low: 'Calm',
}

export const VOLATILITY_MEANING: Record<Volatility, string> = {
  high: 'Prices swing a lot day to day. Expect a rougher ride.',
  moderate: 'Day-to-day price swings are about average for a stock.',
  low: 'Prices have been steady, with small daily moves.',
}

export const VELOCITY_LABEL: Record<MentionVelocity, string> = {
  rising: 'Getting more attention',
  falling: 'Losing attention',
  steady: 'Steady attention',
  unknown: 'Not measured',
}

/**
 * Describe how much to trust a signal.
 *
 * Confidence is capped at 95 by the engine, and a technicals-only reading
 * rarely clears 60 — so the bands are set against what is actually achievable
 * rather than against a naive 0-100 scale.
 */
export function describeConfidence(confidence: number): { label: string; meaning: string } {
  if (confidence >= 70) {
    return {
      label: 'High confidence',
      meaning: 'The different measures agree strongly with each other.',
    }
  }
  if (confidence >= 45) {
    return {
      label: 'Moderate confidence',
      meaning: 'The measures mostly agree, but not completely.',
    }
  }
  if (confidence >= 25) {
    return {
      label: 'Low confidence',
      meaning: 'The measures disagree, or some information is missing.',
    }
  }
  return {
    label: 'Very low confidence',
    meaning: 'There is not enough agreement here to read much into it.',
  }
}

/** Score out of 100 as a word, for the technical and sentiment ratings. */
export function describeScore(score: number): string {
  if (score >= 75) return 'Strong'
  if (score >= 60) return 'Good'
  if (score >= 40) return 'Average'
  if (score >= 25) return 'Weak'
  return 'Very weak'
}

export function toneForScore(score: number): Tone {
  if (score >= 75) return 'positive'
  if (score >= 60) return 'mild-positive'
  if (score >= 40) return 'neutral'
  if (score >= 25) return 'mild-negative'
  return 'negative'
}

/** Format a price in US dollars. */
export function formatPrice(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

/** Format a percentage change with an explicit sign. */
export function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

/** Compact volume, e.g. 49.4M. */
export function formatVolume(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(value)
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

/**
 * Glossary for the "what does this mean?" affordances.
 *
 * Each entry pairs the technical name with an explanation that stands on its
 * own — the reader should never need to look anything else up.
 */
export const GLOSSARY: Record<string, { term: string; plain: string }> = {
  momentum: {
    term: 'Momentum (RSI)',
    plain:
      'Measures how one-sided recent trading has been, from 0 to 100. Very high means buyers have been dominant and the move may be stretched; very low means the opposite.',
  },
  trendStrength: {
    term: 'Trend strength (ADX)',
    plain:
      'Measures how committed a price move is, from 0 to 100. Above 25 suggests a real trend; below 20 suggests the price is just drifting around.',
  },
  movingAverage: {
    term: 'Moving average',
    plain:
      'The average closing price over a set number of days. Traders watch whether the current price sits above or below it to judge direction.',
  },
  goldenCross: {
    term: 'Golden cross',
    plain:
      'When the 50-day average rises above the 200-day average. Widely watched as a sign that a longer-term uptrend may be starting.',
  },
  deathCross: {
    term: 'Death cross',
    plain:
      'When the 50-day average falls below the 200-day average. The mirror image of a golden cross, and read as a warning sign.',
  },
  volatility: {
    term: 'Volatility',
    plain:
      'How much the price bounces around day to day. Higher volatility means bigger swings in both directions.',
  },
  technicalScore: {
    term: 'Chart score',
    plain:
      'Our 0-100 summary of what the price chart shows: trend, momentum, and where the price sits in its recent range.',
  },
  sentimentScore: {
    term: 'Mood score',
    plain:
      'Our 0-100 summary of how people are talking about this stock in news articles and social posts.',
  },
  overallScore: {
    term: 'Overall score',
    plain:
      'The chart score and mood score combined into one number. When mood data is unavailable, this is the chart score alone.',
  },
}
