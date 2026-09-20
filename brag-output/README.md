# brag-output

A launch video for Quantimental, made with the [`/brag`](https://github.com/latent-spaces/brag)
Claude Code skill, which hands a storyboard to [Hyperframes](https://hyperframes.heygen.com/)
to build and render.

| File | What it is |
| --- | --- |
| `brag.mp4` | The video. 1920x1080, 30fps, 24.8s, H.264 + AAC. |
| `brag.jpg` | The poster frame, also baked in as frame 0 so thumbnail grabbers use it. |
| `brag-plan.md` | The creative plan and storyboard — the contract the video was built against. |
| `composition-brief.md` | The handoff brief, plus what was actually built and how it was verified. |
| `share-copy.txt` | The caption. |
| `composition/` | The Hyperframes project. `index.html` is the whole composition. |

## What the video does

A descent. It opens on the whole market (`signal-desk.tsx` — the narrative line, the risk
appetite composite, the not-a-forecast disclaimer), narrows through the sector strip
(`sector-strip.tsx` — the centre-line bars), isolates Information Technology, and lands inside
it on a single Oracle card (`stock-card.tsx`). Only after the product has visibly done its job
does the film say what it refuses to do: the 48.5% backtest, and the ratings deleted rather
than tuned.

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

Then re-pick the poster and bake it back in as frame 0:

```bash
cd ..
ffmpeg -y -ss 14.5 -i brag.mp4 -frames:v 1 -q:v 2 brag.jpg
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
