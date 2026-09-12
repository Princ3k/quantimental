/**
 * Backend API client.
 *
 * One thin fetch wrapper plus typed helpers. Every function either resolves
 * with data or throws an ApiError carrying a message that is safe — and
 * useful — to show a user.
 */

import type {
  AnalyzeResponse,
  BatchResponse,
  SearchResponse,
  SignalDeskResponse,
  StockSignal,
  TickerNewsResponse,
} from './types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/** How long any single request may take before it is abandoned. */
const REQUEST_TIMEOUT_MS = 30_000

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly isNetworkError = false,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface RequestOptions extends Omit<RequestInit, 'signal'> {
  /** Abort signal from the caller, merged with the internal timeout. */
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  // Respect a caller's own abort (e.g. a superseded search keystroke) while
  // still enforcing the timeout.
  options.signal?.addEventListener('abort', () => controller.abort(), { once: true })

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })

    const raw = await response.text()
    const body = raw ? safeJsonParse(raw) : null

    if (!response.ok) {
      throw new ApiError(extractMessage(body, response.status), response.status)
    }

    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error

    if (error instanceof DOMException && error.name === 'AbortError') {
      // A caller-initiated abort is not a failure worth reporting.
      if (options.signal?.aborted) throw error
      throw new ApiError('The request took too long. Please try again.', 0, true)
    }

    // Deliberately not "check the backend is running" — that is advice for a
    // developer on localhost, and meaningless to someone visiting the site.
    throw new ApiError(
      "We couldn't reach our servers. Check your connection and try again.",
      0,
      true,
    )
  } finally {
    clearTimeout(timeout)
  }
}

function safeJsonParse(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/**
 * Pull a displayable message out of an error body.
 *
 * FastAPI returns `detail` as a string for HTTPException and as an array of
 * objects for validation errors, so both shapes are handled.
 */
function extractMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail

    if (typeof detail === 'string') return detail

    if (Array.isArray(detail)) {
      const first = detail[0]
      if (first && typeof first === 'object' && 'msg' in first) {
        return String((first as { msg: unknown }).msg)
      }
    }
  }

  if (status === 404) return 'We could not find that stock.'
  if (status >= 500) return 'The server had a problem. Please try again shortly.'
  return 'Something went wrong.'
}

/** Analyze one stock in depth, including news and social sentiment. Slow. */
export async function analyzeStock(ticker: string, signal?: AbortSignal): Promise<StockSignal> {
  const response = await request<AnalyzeResponse>('/api/v1/signals/analyze', {
    method: 'POST',
    body: JSON.stringify({ ticker }),
    signal,
  })

  if (!response.signal) {
    throw new ApiError(response.error ?? 'No data available for this stock.', 404)
  }
  return response.signal
}

/**
 * Analyze several stocks at once.
 *
 * Defaults to `fast` depth: real prices and technicals, no sentiment. That is
 * what a dashboard wants — a dozen tickers in about a second.
 */
export async function analyzeBatch(
  tickers: string[],
  depth: 'fast' | 'full' = 'fast',
  signal?: AbortSignal,
): Promise<BatchResponse> {
  return request<BatchResponse>(`/api/v1/signals/batch?depth=${depth}`, {
    method: 'POST',
    body: JSON.stringify({ tickers }),
    signal,
  })
}

/** Search for tickers. An empty query returns curated suggestions. */
export async function searchTickers(query: string, signal?: AbortSignal): Promise<SearchResponse> {
  return request<SearchResponse>(
    `/api/v1/signals/search?q=${encodeURIComponent(query)}`,
    { signal },
  )
}

/** Recent news for one ticker. Returns an empty list when unavailable. */
export async function getTickerNews(
  ticker: string,
  limit = 4,
  signal?: AbortSignal,
): Promise<TickerNewsResponse> {
  return request<TickerNewsResponse>(
    `/api/v1/news/ticker/${encodeURIComponent(ticker)}?limit=${limit}`,
    { signal },
  )
}

/** Check whether the backend is reachable and healthy. */
export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const body = await request<{ status: string }>('/health', { signal })
    return body.status === 'healthy'
  } catch {
    return false
  }
}

/**
 * The market-wide Signal Desk.
 *
 * Needs no ticker — it reads a fixed basket of rates, credit, currency,
 * commodity, volatility and sector instruments and reports the state of the
 * market as a whole.
 */
export async function getSignalDesk(signal?: AbortSignal): Promise<SignalDeskResponse> {
  return request<SignalDeskResponse>('/api/v1/market/signal-desk', { signal })
}
