# Hyperframes Composition Brief: Quantimental

*(v2 — re-cut as a descent: whole market → sectors → one stock, `polished` tone, the
ratings story moved from the hook to the turn.)*

## Objective
Create a short launch-style brag video for Quantimental — a market-description product whose
defining move was deleting its own buy/sell ratings after backtesting them.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 24.8 seconds (as built)

## Source Material
- Project root: `/home/user/quantimental`
- Primary files read: `README.md`, `frontend/app/globals.css`, `frontend/app/layout.tsx`,
  `frontend/app/method/page.tsx`, `frontend/components/stock-card.tsx`,
  `frontend/components/ticker-search.tsx`, `frontend/components/dashboard.tsx`
- Product name: **Quantimental**
- Tagline / strongest claim: "Why stocks moved today, described rather than predicted."
- Key UI to recreate: the market overview (`signal-desk.tsx` — narrative line, `RISK APPETITE`
  composite, the not-a-forecast disclaimer), the **sector strip** (`sector-strip.tsx` — the
  centre-line bar growing either side of a hairline axis, breadth ratio, median move), and the
  stock card (`stock-card.tsx` — company + mono ticker, large tabular percentage in the
  direction colour, and `Figure` blocks whose notes sit visibly under the value).
- Copy that must appear verbatim:
  - `MARKET TODAY` / `The market rose 0.5% today.` / `Eight of eleven sectors rose with it.`
  - `RISK APPETITE` / `61 / 100` / `Measured`
  - `Describes moves that have already happened. Not a forecast, not advice.` (verbatim from
    `signal-desk.tsx`)
  - `ALL SECTORS` / `median move · how many rose` (verbatim from `sector-strip.tsx`)
  - The six sector rows with breadth ratios and median moves
  - `Oracle Corporation` / `ORCL` / `−1.7%` / `today`
  - `and down 1.1% over the past two weeks`
  - `WHAT WE READ` / `MARKET +0.5%` / `ITS SECTOR +1.9%` / `NEWS VOLUME 41/day`, each with its
    note visible beneath the value
  - `Oracle did not follow its sector.`
  - `8-K · quarterly results, filed after the previous close`
  - `THE RATINGS IT USED TO PUBLISH` / `48.5%` / `DIRECTIONAL ACCURACY · A COIN FLIP IS 50%` /
    `Deleted rather than tuned.`
  - `Quantimental` / `Described, not predicted.` / `thequantimental.com`

## Creative Direction
- Tone preset: `polished`
- Creative direction: a quiet instrument demonstrating itself — wide to narrow, one idea per
  frame, the product's own restraint as the style.
- Interpretation: slow 0.70s crossfades between every scene, no hard cuts anywhere. Motion is
  scale and descent, never flourish: nothing zooms, bounces or glows. Medium-weight mixed-case
  type, real holds. The one place the film allows itself force is the beat where the sectors
  fall away.
- Angle: A descent. Start where the product starts — the whole market in one line — narrow to
  eleven sectors, isolate the one that moved, and land inside it on one company and one
  sentence. Only once the product has visibly done its job does the film say what it refuses to
  do; at the end that reads as a principle rather than an apology.
- Hook: the eyebrow `MARKET TODAY` and one large line, `The market rose 0.5% today.`, with a
  `61 / 100` risk-appetite score behind a hairline. A real reading, at full scale, no setup.
- Outro / punchline: `48.5%` · `DIRECTIONAL ACCURACY · A COIN FLIP IS 50%` · `Deleted rather
  than tuned.`, then the wordmark.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - **Specifically:** gradients, glows, blurred blobs, drop shadows of any weight, rounded
    "card inside card" nesting, decorative accent colour, ticker-tape or candlestick clip art,
    animated line charts, confetti, particles, cursor graphics, or any colour that is not
    carrying direction. The project's design system bans all of these in its own comments.

## Visual Identity
From `frontend/app/globals.css` `:root` (light theme) — use these exact values:
- Background: `oklch(0.985 0.002 85)`
- Surface: `oklch(1 0 0)`
- Text (ink): `oklch(0.18 0.004 60)`
- Secondary text (ink-2): `oklch(0.44 0.006 70)`
- Hairline rule: `oklch(0.90 0.004 75)`; strong: `oklch(0.82 0.005 75)`
- Down / red: `oklch(0.53 0.155 27)`
- Up / green: `oklch(0.52 0.115 155)`
- Mark: `oklch(0.28 0.02 60)`
- Radius: `0.5rem` (used only on the search input and card, nowhere else)
- Display font: **Inter Tight** (`h1` letter-spacing `-0.032em`, `h2/h3` `-0.022em`)
- Body font: Inter Tight
- Figures font: **JetBrains Mono** with `font-variant-numeric: tabular-nums` — every number
  in the film is mono and tabular
- `.eyebrow`: JetBrains Mono, uppercase, `letter-spacing: 0.14em`, quiet, small. This is the
  structural label in every scene.
- Visual references from the project: hierarchy from type size only; sections separated by
  space and hairlines, never boxes; numbers are large and monospaced because "they are what
  people came for"; one idea per surface.

**Contrast:** `ink-3` (`oklch(0.62 0.006 75)`) is the project's quietest grey and will likely
fail the WCAG gate at small sizes. Use `ink-2` for anything that must be read. If `check`
reports a contrast error, darken within the warm-neutral family (toward `mark` /
`oklch(0.28 0.02 60)`) rather than introducing a new hue.

**Fonts:** prefer locally available Inter Tight / JetBrains Mono; if the renderer cannot resolve
them, fall back to a tight grotesque and a tabular mono respectively and note the substitution.
Do not substitute a serif — the project is explicitly not a serif broadsheet, it only behaves
like one.

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. **The whole market** — 4.5s (0.0→4.5) — `MARKET TODAY`; `The market rose 0.5% today.` with
   the figure inline in tabular mono; `Eight of eleven sectors rose with it.`; the
   `RISK APPETITE 61 / 100 · Measured` block behind a hairline; the verbatim not-a-forecast line.
2. **Eleven sectors, then one, then the company inside it** — 11.3s (4.5→15.8) — six sector rows
   cascade in and are read as a set; at 8.74s all but Information Technology recede and clear,
   and that row lifts; at 9.83s the Oracle card rises into its place; the card opens and fills
   with the fortnight line, three readings, the conclusion and the 8-K chip.
3. **What it will not tell you** — 5.5s (15.8→21.3) — `THE RATINGS IT USED TO PUBLISH`; `48.5%`
   at 18.56s with `DIRECTIONAL ACCURACY · A COIN FLIP IS 50%`; `Deleted rather than tuned.`
4. **Quantimental** — 3.5s (21.3→24.8) — wordmark, hairline, tagline, URL, then stillness.

Readability floors are stated per scene in the plan and are not negotiable — if a tween cannot
hit its beat lock without eating a line's settled time, drop the lock and use natural timing.

## Audio
- Audio role: sparse professional accents over a very low bed; the bed is furniture.
- Audio arc: bed in at level from 0.0 → two dry clerical placements in Scene 2 → the film's only
  textured moment (typing + card landing) in Scene 3 → one placement on the 8-K chip in Scene 4
  → bed fades from ~19.5s to zero by ~21.6s so the wordmark hold ends in silence.
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3`
- Music treatment: **0.24** flat via the volume lane, fade out 20.8s→24.2s.
- Music cue guidance: bundled preset — copy/read
  `~/.claude/skills/brag/assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`
  (tempo 109.96, planning window 0–25s). Three strong-cue locks only:
  - **8.74s** — the sectors recede; the descent begins → `// beat-locked: 8.74s`
  - **13.11s** — `Oracle did not follow its sector.` lands → `// beat-locked: 13.11s`
  - **18.56s** — `48.5%` lands → `// beat-locked: 18.56s`
  Beat-grid (every *other* beat — readable text must not ride consecutive beats at 110 BPM):
  - Sector rows cascade from 5.34s (0.12s stagger, read as one set) → `// beat-grid`
  - Card body opens 10.93s; the three readings arrive 12.02s → `// beat-grid`
- Audio-reactive treatment: **subtle, verging on none** — at most a few percent of warmth on the
  paper background or hairline opacity driven by RMS. No glow, no scale, no waveform,
  no equalizer, no particles. If extraction is unavailable, skip it and note it; do not block
  the render, and do not substitute a fake pulse.
- Audio-coupled moments:
  - Scene 1, figure settles — one very quiet dry placement, or none if it reads as a sting
  - Scene 2, verdict rows — dry placement per row (beat-grid)
  - Scene 2, the swap to `So we deleted the ratings.` — **silence**, deliberately
  - Scene 3, `ORCL` typing — randomised individual keypresses, low
  - Scene 3, card landing — one soft impact, the largest sound in the film
  - Scene 4, `8-K` chip — one dry placement; the two lines arrive silent
  - Scene 5, wordmark — one restrained accent or nothing
- SFX selection guidance: 4–6 cues total in 22 seconds. Dry, low, clerical. Use
  `keyboard/keypress-*.wav` randomised for the typed ticker, `interface/drop_*` or
  `interface/select_008` for placements and the row selection, and a single
  `impact/impactSoft_medium_*` for the card landing. **No** bells, chimes, dings, risers,
  whooshes, glitches, or `chips-collide` celebration. SFX volume 0.45–0.60 — below the audio
  reference's normal floor, because this tone asks for it.
- SFX analysis guidance: `~/.claude/skills/brag/assets/sfx/sfx-analysis.md` — prefer low
  high-frequency-risk files; every cue here is a repeated or polished moment.
- Exact SFX choice: Hyperframes chooses filenames, timestamps, density and volume after the
  animation exists.
- Audio files: copy the chosen music and SFX into `brag-output/composition/assets/`
  (`assets/music/`, `assets/sfx/...`) and reference them with paths relative to
  `composition/`. Never absolute paths.

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition
contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design
spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and
`hyperframes-cli` (lint/check/render). /brag is its own workflow: do not enter the `hyperframes`
entry-point intent interview and do not route into its generic promo / launch-video workflow.
Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI element from the source project — here, the search field and the
  stock card, rebuilt from the actual components and the actual design tokens.
- Keep all text readable in the final render; honour the per-scene reading floors in the plan.
- Keep the video within 15-25 seconds (built at 24.8s).
- Include the planned music/SFX layer.
- Treat `/brag` audio notes as guidance, not a fixed cue sheet. Choose SFX after the visual
  animation exists.
- Treat music cue metadata as optional timing hints; ignore any cue that hurts readability,
  pacing, or the product story.
- Use only 3 strong-cue locks (listed above) and the two beat-grid windows.
- Music bed on a low track index; each overlapping SFX gets its own ascending track index.
- Run `hyperframes check` before render and fix every error, including WCAG contrast.



---

## Built

`composition/index.html`, monolithic (one file, four `.clip` sections, one paused GSAP timeline
built inside `document.fonts.ready` so the card body can be measured against real font metrics).

`npx hyperframes check` → **0 errors**, 4 warnings, 0 layout issues across 9 samples. The four
warnings are all `nested_structure_needs_subcomposition` — Studio-ergonomics advice about
splitting scenes into sub-composition files. Monolithic is a supported shape and the render is
unaffected.

The contrast pass reports `0/0 text checks`, i.e. it sampled nothing rather than passing
nothing, so contrast was verified by hand against WCAG 2.1 instead: every foreground/background
pair in the film clears AA at normal size (ink 18.0:1, ink-2 8.1:1, up 7.0:1, down 7.1:1 on the
paper background; all higher on the white card).

Audio-reactive treatment is deliberately **absent**, not skipped for lack of tooling: the
palette has no glow, depth or decorative layer to modulate, and inventing one to carry
audio-reactivity would break the project's own rule that colour carries meaning or is absent.

Rendered at `--quality delivery`: 1920x1080, 30fps, 744 frames, 24.8s, H.264 + AAC. The poster
is the fully-assembled Oracle card at 14.5s, baked as frame 0 so thumbnail grabbers use it.
