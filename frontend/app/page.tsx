import { Dashboard } from '@/components/dashboard'
import { getSectorSummaries } from '@/lib/sectors'

/*
 * Sectors are read here, on the server, from the static snapshot — not fetched
 * by the dashboard. It costs no API call, needs no loading state, and is in
 * the HTML a crawler sees.
 */
export const revalidate = 1800

export default async function HomePage() {
  return <Dashboard sectorRows={await getSectorSummaries()} />
}
