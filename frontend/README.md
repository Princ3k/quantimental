# Quantimental Frontend

Next.js 16 dashboard. See the [repository README](../README.md) for the
project overview.

## Run it

```bash
npm install
npm run dev
```

Expects the backend on <http://localhost:8000>. Point it elsewhere with
`NEXT_PUBLIC_API_URL` (see `.env.example`).

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Development server |
| `npm run build` | Production build — fails on type errors |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint |
| `npm run check` | Both of the above |

## Layout

```
app/
├── layout.tsx            Root layout + the pre-paint theme script
├── page.tsx              Renders <Dashboard />
└── globals.css           Design tokens for both themes
components/
├── dashboard.tsx         Data fetching and page composition
├── stock-card.tsx        One stock, in reading order
├── how-to-read.tsx       First-run explainer of the five verdicts
├── verdict.tsx           The Buy/Hold/Sell pill and confidence meter
├── score-bar.tsx         A 0-100 score, or an explanation when unavailable
├── info-tip.tsx          The "what does this mean?" glossary affordance
└── ui/                   shadcn-style primitives
lib/
├── api.ts                Typed backend client
├── types.ts              The backend's JSON contract
├── presentation.ts       Plain-English wording and formatting
├── use-local-storage.ts  localStorage as a React external store
└── use-watchlist.ts      The user's list, persisted per browser
```

## Design notes

**Reading order on a card.** Which company → what it did today → the verdict →
why, in one sentence → how much to trust it → everything else, collapsed. A
first-time investor should get value from the first two lines without opening
anything.

**No bare jargon.** Indicator names appear only inside an `<InfoTip>` next to a
definition. Where a raw value is still useful it is renamed to something
self-explanatory: "momentum" for RSI, "trend strength" for ADX. The wording for
a given reading comes from the backend, so a card cannot contradict itself.

**Missing data is shown, not filled.** When sentiment is unavailable the mood
score renders an explanation instead of a bar. Drawing a half-full bar for a
placeholder 50 makes a non-measurement look like a measurement.

**Colour is never the only signal.** Every verdict pairs a colour with an icon
and a word, so it survives greyscale and colour vision deficiency.

**localStorage via `useSyncExternalStore`.** Reading storage in an effect and
calling `setState` causes a cascading render on every mount, which React 19's
lint rules flag. The external-store hook is the right primitive, and it syncs
across browser tabs for free.
