# Brag Plan: Quantimental

*(v2 — re-cut. The first pass opened on the 48.5% failure number in the `deadpan` tone. This
one opens wide on the whole market and descends to a single stock, in `polished`, with the
ratings story moved from the hook to the turn.)*

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
