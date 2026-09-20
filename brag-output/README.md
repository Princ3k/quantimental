# brag-output

A launch video for Quantimental, made with the [`/brag`](https://github.com/latent-spaces/brag)
Claude Code skill, which hands a storyboard to [Hyperframes](https://hyperframes.heygen.com/)
to build and render.

| File | What it is |
| --- | --- |
| `brag.mp4` | The landscape cut. 1920x1080, 30fps, 27.2s, H.264 + AAC. |
| `brag.jpg` | Its poster frame, also baked in as frame 0 so thumbnail grabbers use it. |
| `brag-vertical.mp4` | The 9:16 cut for Stories / Reels / TikTok. 1080x1920, same length. |
| `brag-vertical.jpg` | Its poster frame, baked in the same way. |
| `build-vertical.py` | Generates the vertical cut from the landscape composition. |
| `brag-plan.md` | The creative plan and storyboard — the contract the video was built against. |
| `composition-brief.md` | The handoff brief, plus what was actually built and how it was verified. |
| `share-copy.txt` | The caption. |
| `composition/` | The Hyperframes project. `index.html` is the whole composition. |
| `composition-vertical/` | Generated. Do not edit by hand — re-run `build-vertical.py`. |

## What the video does

Noise, then a descent. All 503 tickers fill the frame and churn; the grid goes quiet and the
film says *"Let's reduce the noise."* Then it keeps that promise — the day's market and sectors,
503 scanned down to the 2 flagged unusual, and one of them (Nucor, down 6.3% on a stock whose
typical day is 2.8%) opened up in full. Only after the product has visibly done its job does the
film say what it refuses to do: the 48.5% backtest drawn as five bucket returns climbing the
wrong way, and the ratings deleted rather than tuned.

The card carries a band showing today against a normal day for Nucor: the shaded range is its
typical ±2.8% move with goalposts at the edges, and today's bar visibly crosses one. That is the
engine's per-stock baseline — a mega-cap moving 3% is news, a small-cap moving 3% is Tuesday —
shown rather than explained.

**Every figure is real.** They come from the committed scan of 2026-09-18 in `public/` —
`snapshot.json`, `signal-desk.json`, `unusual.json` and `backtest.json` — because the first
design rule in the root README is that nothing is invented.

Colours and fonts are the project's own, from `frontend/app/globals.css` and
`frontend/app/layout.tsx`. The three text colours are darkened 0.02–0.08 L from the source
tokens so every pair clears WCAG AA at normal size.

## Re-rendering

Needs Node 22+, FFmpeg, and a headless Chrome (`npx hyperframes browser ensure`).

```bash
cd composition
npx hyperframes check                              # lint + runtime + layout + contrast
npx hyperframes render --quality delivery --output ../brag.mp4
```

The vertical cut is generated from the landscape one, so edit `composition/` and regenerate:

```bash
python3 build-vertical.py
cd composition-vertical
npx hyperframes check
npx hyperframes render --quality delivery --output ../brag-vertical.mp4
```

Then re-pick the poster and bake it back in as frame 0:

```bash
cd ..
ffmpeg -y -ss 18.5 -i brag.mp4 -frames:v 1 -q:v 2 brag.jpg
ffmpeg -y -i brag.mp4 -i brag.jpg \
  -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]" \
  -map "[v]" -map 0:a? -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
  -c:a copy -movflags +faststart out.mp4 && mv out.mp4 brag.mp4
```

`composition/assets/` is committed so this works from a clean clone. It holds Inter Tight and
JetBrains Mono (SIL OFL, Google Fonts), GSAP, one music bed, and four sound effects.

## Credits

- Music — "Happy Beats / Business Moves" by [ende.app](https://ende.app/en)
- Sound effects — [Kenney](https://kenney.nl/) (CC0)
- Video framework — [Hyperframes](https://hyperframes.heygen.com/)
