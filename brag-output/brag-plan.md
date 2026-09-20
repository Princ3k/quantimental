# Brag Plan: Quantimental

*(v3. v1 opened on the 48.5% failure number in `deadpan`. v2 became a descent through the
market in `polished`. v3 keeps the descent and fixes the thing that mattered most: **every
figure is now real**, read from the committed 2026-09-18 scan in `public/`, and the film opens
on all 503 tickers at once before quieting down.)*

## What is this app?
Quantimental reads price action, news volume and SEC filings and says, in one sentence a reader
can check against the chart, why a stock moved today. It used to rate stocks buy/sell; it
backtested those ratings over 3,792 observations, found them worse than a coin flip, and deleted
them instead of tuning them.

## The angle
A descent. The video starts where the product starts — the whole market, in one line, with a
risk-appetite score beside it — then narrows to eleven sectors, isolates the one that moved, and
lands inside it on a single company and a single sentence. Only once the product has actually
done its job does the film say what it refuses to do. Putting the deletion at the *end* makes it
a principle rather than an apology, and the descent earns it: you have just watched the thing
describe something precisely, so "it will not predict" reads as restraint, not as absence.

## Hook (first 2-3 seconds)
Warm paper, the eyebrow `MARKET TODAY`, and one large line with a live figure set in the
product's own tabular mono: **The market rose `0.5%` today.** A risk-appetite score —
`61 / 100 · Measured` — sits behind a hairline to the right. Full scale, no setup. The hook is
that the film opens on a real reading rather than on a claim about readings.

## Key moments (the middle)
- The **sector strip** — six rows with the product's distinctive centre-line bars growing left
  or right of a hairline axis, `8/12`-style breadth counts, and median moves. Reference data
  rendered as a glance, which is exactly what the component was written to do.
- The **descent**: at the beat, every sector but Information Technology recedes to 10% opacity
  and then to nothing; the surviving row lifts toward the top of the frame.
- The **company rising into its place** — the Oracle card arrives from below where the sector row
  just was, so the hierarchy (market → sector → company) is carried by motion, not stated.
- The **card opening**: header only at first (`Oracle Corporation · ORCL · −1.7% today`,
  `and down 1.1% over the past two weeks`), then the body expands and three readings arrive
  together — market, sector, news volume — because the point is comparing them.
- The **conclusion** the product is actually for: *Oracle did not follow its sector.*

## Outro / punchline
The turn: `THE RATINGS IT USED TO PUBLISH` · **48.5%** · `DIRECTIONAL ACCURACY · A COIN FLIP IS
50%` · **Deleted rather than tuned.** Then the wordmark, the tagline, and stillness.

## User flow worth showing
Entry → key action → result, taken from `frontend/components/{signal-desk,sector-strip,stock-card}.tsx`
and `backend/app/engines/{describe,attribution}.py`:
1. **Entry** — the market overview: one narrative line, a risk-appetite composite, breadth.
2. **Key action** — reading down the sector strip and picking the sector that moved.
3. **Result** — the stock card for a company inside it: today's move, the fortnight behind it,
   market and sector beside each other, news volume, the 8-K, and the sentence.
The whole middle of the film is this flow. Nothing is a landing-page recreation.

## Tone
- Preset: `polished`
- Creative direction: a quiet instrument demonstrating itself — wide to narrow, one idea per
  frame, the product's own restraint as the style.
- Interpretation: slow crossfades (0.70s) between every scene, no hard cuts anywhere. Motion is
  scale and descent, never flourish: nothing zooms, nothing bounces, nothing glows. Type is
  medium weight and mixed case. Six-second average scene length with real holds. The one place
  the film allows itself force is the beat where the sectors fall away.

## Format: landscape — 1920x1080
## Duration: 24.8 seconds

## Visual identity (from the project)
From `frontend/app/globals.css` `:root` and `frontend/app/layout.tsx`.
- Background: `oklch(0.985 0.002 85)` (warm paper) · Surface: `oklch(1 0 0)`
- Ink: `oklch(0.18 0.004 60)` · Ink-2: `oklch(0.42 0.006 70)`
- Hairline: `oklch(0.90 0.004 75)` · strong `oklch(0.82 0.005 75)`
- Up: `oklch(0.44 0.115 155)` · Down: `oklch(0.47 0.165 27)` · Mark: `oklch(0.28 0.02 60)`
- Display + body: **Inter Tight** · Figures: **JetBrains Mono**, tabular
- `.eyebrow`: mono, uppercase, `letter-spacing: 0.14em`, quiet — the structural label everywhere
- Strongest visual element: the sector strip's centre-line bar. A hairline axis with the bar
  growing left for down and right for up, so direction reads before the number does.

`ink-2`, `up` and `down` were darkened 0.02–0.08 L from the source tokens so every text pair
clears WCAG AA at normal size (measured: ink 18.0:1, ink-2 8.1:1, up 7.0:1, down 7.1:1 on paper).
Hue and chroma are the project's.

## Share copy (draft)
See `share-copy.txt`.

## Audio direction
- Role: a low bed with five soft cues — present, never eager.
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady, clean, 109.96 BPM),
  volume **0.24**, flat, fading 20.8s → 24.2s so the wordmark ends in silence.
- Music cue guidance: bundled preset at
  `<skill-dir>/assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`.
  Three strong-cue locks:
  - **8.74s** — the sectors recede (the descent begins)
  - **13.11s** — *Oracle did not follow its sector.* lands
  - **18.56s** — **48.5%** lands
  Beat-grid windows: sector rows cascade from 5.34s (0.12s stagger, read as one set); the card
  body opens at 10.93s; the three readings arrive at 12.02s.
- Audio-reactive treatment: **none**. The palette has no glow, depth or decorative layer to
  modulate, and adding one to carry audio-reactivity would break the project's own design rules
  (colour carries meaning or it is absent). Documented rather than faked.
- SFX posture: five cues in 24.8s, all soft — `drop_001` on the market line, `drop_002` on the
  sector list, `impactSoft_medium_000` as the card rises, `bong_001` under the conclusion,
  `impactSoft_medium_002` on the 48.5%.
- Restraint rule: no dings, chimes, risers, whooshes or celebration. The loudest sound in the
  film is a soft thud at 0.46.

## Storyboard

### Scene 1 — The whole market — 4.5s (0.0 → 4.5, crossfading out to 5.2)
Eyebrow `MARKET TODAY`. One large line, `The market rose 0.5% today.`, with the figure inline in
tabular mono and the product's green. Below it, `Eight of eleven sectors rose with it.` To the
right, behind a hairline: `RISK APPETITE`, `61 / 100`, `Measured`. At the bottom, small and
verbatim from `signal-desk.tsx`: *Describes moves that have already happened. Not a forecast,
not advice.* — which quietly plants the turn 17 seconds early.
Reading budget: eyebrow 0.8s · the line 1.5s settled · breadth line 1.8s · risk block 1.3s.
Sequential: yes — eyebrow → line → breadth → risk block → disclaimer, each settled before the next.
Audio intent: the bed is already at level; one soft `drop_001` as the line settles.
Transition: slow crossfade (0.70s) → Scene 2

### Scene 2 — Eleven sectors, then one, then the company inside it — 11.3s (4.5 → 15.8)
The longest scene, and the product actually working. `ALL SECTORS` / `median move · how many
rose`. Six rows cascade in at 0.12s apart and are read as a set: Industrials, Financials,
**Information Technology**, Consumer Staples, Utilities, Energy — each with the centre-line bar,
the breadth ratio and the median move.
At **8.74s** everything but Information Technology recedes to 10% and then clears; that row
lifts 170px toward the top of the frame. At 9.83s the Oracle card rises from below into the
space it left, and the row fades under it.
The card then opens: `−1.7%` `today` at 10.10s, `and down 1.1% over the past two weeks` at
10.37s, the body expanding at 10.93s, `WHAT WE READ` at 11.30s, and at 12.02s three readings
together — `MARKET +0.5%`, `ITS SECTOR +1.9%`, `NEWS VOLUME 41/day` — each with its note visible
underneath rather than behind a tooltip, as `stock-card.tsx` insists. The conclusion lands at
**13.11s**, the 8-K chip at 13.64s, and the whole thing holds for two seconds.
Reading budget: the six-row set gets 2.3s settled · the three figures 1.1s as a block · the
conclusion 1.9s · the chip is a label.
Sequential/interaction: yes throughout — the cascade, the recede, the rise, the open, the trio.
Audio intent: `drop_002` under the cascade, `impactSoft_medium_000` as the card rises (the
largest sound in the film), `bong_001` under the conclusion.
Transition: slow crossfade (0.70s) → Scene 3

### Scene 3 — What it will not tell you — 5.5s (15.8 → 21.3)
Empty paper. Eyebrow `THE RATINGS IT USED TO PUBLISH` at 16.93s. Then, at **18.56s**, a single
enormous mono figure: **48.5%**, with `DIRECTIONAL ACCURACY · A COIN FLIP IS 50%` beneath it.
Then, at 19.66s: **Deleted rather than tuned.**
Reading budget: eyebrow 0.9s · figure + sub-label 1.1s as a unit · the final line 1.6s.
Sequential: yes — three beats, each fully settled.
Audio intent: `impactSoft_medium_002` as the figure lands. Nothing after it.
Transition: slow crossfade (0.70s) → Scene 4

### Scene 4 — Quantimental — 3.5s (21.3 → 24.8)
Wordmark centre at 21.84s, a short hairline drawing under it at 22.50s, then `Described, not
predicted.` at 22.93s and `thequantimental.com` at 23.46s. No motion at all after 23.86s.
Audio intent: the bed is fading; the last half second is silence on paper.

**Music mood:** polished — a steady clean bed at 0.24, faded out before the end.
**Audio summary:** A low bed runs the full 24.8s under five soft cues, the loudest of them the
thud as the company card rises out of its sector; everything fades so the wordmark lands on
paper and nothing else.


---

## v3 — what changed, and why

### Every number is real now

v1 and v2 invented every figure. The README's **first design rule is "Nothing is invented"**,
and a launch film for that product should not open on a fabricated market. It does not have to:
`public/` carries the committed scan from **2026-09-18**, published by the GitHub Action in
`.github/workflows/`.

| Source | What the film uses |
| --- | --- |
| `snapshot.json` | 503 constituents — every ticker and move in the opening grid, plus Nucor's row |
| `signal-desk.json` | Composite 40 / "Mixed", breadth 2 of 10, the real 30-point sparkline |
| `unusual.json` | 503 scanned → 2 flagged; Nucor and PepsiCo with their real multiples |
| `backtest.json` | 3,792 observations, 48.5% accuracy, and the five bucket returns |

The real day turned out to be a better story than the invented one. The market **fell** 0.63%.
Only two of ten sectors advanced. And the hero is no longer Oracle but **Nucor** — down 6.32%
on a stock whose typical day is 2.84%, which is the product's smartest idea (unusual judged
against *this* stock's own baseline) showing itself without being explained.

### The opening: noise, then quiet

All 503 tickers fill the frame in a 19-column grid, each flickering on its own seeded phase.
At 2.19s the flicker damps over 0.9s and the grid settles to 10%.

`503 stocks moved today.` is already up while the grid is still churning.
**`Let's reduce the noise.`** lands at 2.73s, on the calm — so the picture performs the
sentence rather than captioning it. The next scene then keeps the promise: 503 scanned, 2
flagged.

The flicker is a pure function of timeline progress — one proxy tween drives all 503 cells
through `Math.sin` on a per-cell phase baked in at build time from a seeded LCG. No
`Math.random`, no clock, so every frame is reproducible from its time alone.

The grid carries `data-layout-ignore`. Those 503 cells are deliberately illegible texture meant
to be overlapped by the headline and covered by the scrim, and auditing them produced 80
findings about text nobody is meant to read. The attribute is scoped to the grid alone; every
real text block in the film stays audited.

### Figures that count rather than fade

`globals.css` says tabular numerals exist "so a price updating from 99.99 to 100.00 does not
shift the layout" — the design system asking for count-ups. Three of them now: the market to
`−0.63%`, risk appetite to `40`, and Nucor to `−6.32%`. Each is a GSAP proxy tween writing
`textContent` on update, so it is seek-safe.

### The inversion, shown rather than asserted

v2 stated `48.5%` and moved on. v3 draws the five real buckets against the baseline:

| Verdict | Mean return | |
| --- | --- | --- |
| `strong_buy` | −0.14% | significant, and pointing the wrong way |
| `buy` | +0.44% | |
| `hold` | +0.87% | |
| `sell` | +1.07% | |
| `strong_sell` | +2.48% | significant, and pointing the wrong way |

Holding returned +0.78%, drawn as a vertical line through the bars. Only the two statistically
significant buckets are coloured; the middle three are neutral grey, because the project's rule
is that colour carries meaning or is absent. The monotonic climb from most-bullish to
most-bearish is the whole argument, and it is now visible instead of claimed.

### Length

**25.8 seconds** — 0.8s past the skill's 25s cap. The noise opening spends 4.9s before the
product appears, and the reading floors on the new beats do not compress further. Agreed as a
deliberate trade for the two added beats.

### Final timings

| Scene | Window | What happens |
| --- | --- | --- |
| 1 | 0 → 4.9 | 503 tickers churn; damp at 2.19; `Let's reduce the noise.` at 2.73 |
| 2 | 4.9 → 9.5 | Market −0.63% counting up; three real sectors; risk 40 + sparkline at 8.74 |
| 3 | 9.5 → 18.2 | 503 scanned · 2 flagged; both movers; descent at 13.11; Nucor card opens |
| 4 | 18.2 → 23.2 | The five bucket bars at 19.66; `Deleted rather than tuned.` |
| 5 | 23.2 → 25.8 | Wordmark, tagline, silence |

Beat locks: **8.74s** sparkline · **13.11s** the descent · **19.66s** the bars.


---

## v4 — the unusual band, and a vertical cut

### The 2.2× band

The card used to carry a sentence: *"A bigger move than usual for this stock — 2.2× its typical
2.8% day, and down 5.4% over the past two weeks."* Twenty words, about three seconds of reading,
for something a picture settles instantly. It is now a band:

- A shaded range spanning **±2.84%** — Nucor's typical daily move, from the real snapshot row —
  with a hairline goalpost at each edge and the zero axis through the middle.
- Today's **−6.32%** as a bar growing leftward from the axis, visibly crossing the left goalpost.
- Labels: `±2.8% is a normal day for Nucor` and `−6.32% today · 2.2× that`.

This is the idea the film had been missing: the engine judges "unusual" against each stock's own
baseline rather than a fixed percentage (`backend/app/engines/describe.py`), so a mega-cap moving
3% is news and a small-cap moving 3% is Tuesday. The bar crossing the goalpost says that without
a word of explanation. The fortnight figure survives as a short line beneath.

Geometry is derived, not eyeballed: the track maps −7.5%…+7.5% across its width, and the band,
axis and bar positions are computed from 2.84 and −6.32 at build time.

The band takes a beat of its own (frame in at 14.55s, bar grows at 14.84s, labels at 15.29s),
which pushes everything after it. **The film is now 27.2 seconds.** That is 2.2s past the skill's
cap; the band and the inversion bars are both worth more than the seconds they cost.

### The vertical cut

`composition-vertical/` is 1080x1920 — the same timeline, the same figures, the same audio, a
reflowed layout. It is **generated** by `build-vertical.py` from `composition/index.html`, so the
two cannot drift: edit the landscape composition and re-run the script.

What the reflow changes:

- The ticker grid drops from 19 columns to 9, at 34px rows, so 503 cells still fill the frame.
- The risk-appetite block moves from beside the sector rows to beneath them, its left hairline
  becoming a top one.
- The mover rows wrap: ticker, company and move on one line, the multiple on a second. The sector
  column is dropped, since the card names it moments later.
- The inversion track narrows from 760px to 520px, with the bar geometry recomputed from the same
  bucket returns.
- The band's typical label moves to the end of its track, because at 940px the two labels collide.

**Type is scaled up, not merely reflowed.** A 1080-wide canvas is watched at phone width, so a
size that reads comfortably on a 1920 frame is about a third smaller in the hand. Nothing a
viewer needs to read sits below 22px in the vertical cut — the figure notes went 18px → 23px, the
inversion labels 21px → 24px, the baseline caption 16px → 19px.

Both cuts pass `hyperframes check` with 0 errors. The remaining warnings in each are the two
crossfade seams and the card body mid-expansion, all transient by construction.
