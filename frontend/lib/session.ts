/**
 * Naming the trading session a figure describes.
 *
 * The snapshot is published once after the close and read all the way through
 * to the next afternoon, so for a good part of every day the newest figures we
 * have are yesterday's — and for a whole weekend, Friday's. The pages rendered
 * that word every number as "today", which is true when the scan has just run
 * and a false statement the rest of the time.
 *
 * It showed up the first Monday this ran: a visitor reading "Nvidia is little
 * changed today" while the live card beside it showed the stock down 2.65%.
 * Both were correct about different days, and nothing on the page said which.
 *
 * So the session is always named, never inferred. Deciding whether a date is
 * "today" needs the reader's timezone and the market calendar, and both are
 * guesses; a date is simply true.
 */

/** "Friday 11 September" — the session these figures describe. */
export function sessionLabel(iso: string | null | undefined): string | null {
  if (!iso) return null

  // Parsed as UTC: a session is a calendar date, not a moment, and letting the
  // reader's timezone shift it backwards would name the wrong day in Asia.
  const date = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return null

  return date.toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  })
}

/** Whether `iso` is the session happening now, in US market terms. */
export function isCurrentSession(iso: string | null | undefined): boolean {
  if (!iso) return false
  // US Eastern is where the session is defined, so compare against the date
  // there rather than wherever the reader happens to be.
  const eastern = new Date().toLocaleDateString('en-CA', {
    timeZone: 'America/New_York',
  })
  return iso === eastern
}
