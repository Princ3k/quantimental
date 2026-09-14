# Deploying Quantimental

Two services, deployed separately from this one repository.

| Service | Host | Root directory | Cost |
| --- | --- | --- | --- |
| Backend (FastAPI) | Railway | `backend` | ~$5/mo (Hobby) |
| Frontend (Next.js) | Vercel | `frontend` | Free (Hobby) |
| Signal Desk data | GitHub Actions → static file | — | Free |

The Signal Desk publishes itself: a scheduled workflow commits
`public/signal-desk.json`, which needs no server at all.

---

## 1. Backend → Railway

**Both platforms default to the repository root, and this is a monorepo. Setting
the root directory is the step that breaks the build if you skip it.**

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
   → `Princ3k/quantimental`.
2. **Settings → Source → Root Directory:** `backend`
3. **Settings → Variables:**

   | Variable | Value |
   | --- | --- |
   | `GROQ_API_KEY` | your Groq key |
   | `CORS_ORIGINS` | your Vercel URL, comma-separated (see step 3 below) |
   | `LOG_LEVEL` | `INFO` |

   Leave `DATABASE_URL` unset. The signal engine needs no database, and the app
   is built to run without one — `/health` reports which subsystems are live.

4. **Settings → Networking → Generate Domain.**

Verify:

```bash
curl https://YOUR-APP.up.railway.app/health
```

Expect `"status": "healthy"` with `"market_data": true`.

`railway.json` already sets the start command (binding `$PORT`), the healthcheck
path, and a restart policy. `.python-version` pins the interpreter to 3.11 —
numpy and pandas ship version-specific wheels, so this matters.

**Resource use:** ~180 MB RAM steady, near-idle CPU between requests. That sits
inside Hobby's included $5 usage credit. Adding Postgres later would push past
it.

## 2. Frontend → Vercel

1. [vercel.com/new](https://vercel.com/new) → import `Princ3k/quantimental`.
2. **Root Directory:** `frontend` (Next.js is detected automatically).
3. **Environment Variables:**

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_URL` | your Railway URL, no trailing slash |

4. Deploy.

## 3. Connect them

Set `CORS_ORIGINS` on Railway to the Vercel domain(s), comma-separated:

```
https://www.thequantimental.com,https://thequantimental.com
```

Vercel preview deployments (`*.vercel.app`) are already matched by a pattern in
`app/main.py`, so only production domains need listing.

A browser request blocked by CORS shows as a network error in the console with
no server-side trace — if the frontend loads but every request fails, check
this first.

## 4. Signal Desk data (already free)

Add `GROQ_API_KEY` under **Settings → Secrets and variables → Actions** in the
GitHub repo so the scheduled workflow can write LLM narratives. Without it the
workflow still runs and falls back to a deterministic template.

Trigger it manually once from the **Actions** tab to confirm it works.

> GitHub disables scheduled workflows on public repositories after 60 days
> without repository activity. Any commit re-arms them.

---

## Costs

| | Monthly |
| --- | --- |
| Railway Hobby | $5 (usage ~$2–3, inside the credit) |
| Vercel Hobby | $0 |
| GitHub Actions | $0 (public repo) |
| **Total** | **$5** |

Free alternatives to Railway all sleep: Render's free tier spins down after 15
minutes with a 30–60 second cold start, and Fly.io discontinued its free tier
in 2024. For a user-facing app that cold start is the whole first impression.

---

## Keeping the scans running

GitHub Actions `schedule` has never fired for this repository. The workflows
are active, the cron parses, the repository is public and is not a fork, and
GitHub Actions reports operational — but across two cron configurations, and a
schedule that sat unchanged for thirty-five hours, not one scheduled run
started. Push and `workflow_dispatch` work every time.

That difference is the whole story. Push and dispatch are events somebody
sends; `schedule` is a queue GitHub sweeps best-effort, and their documentation
says a run it cannot start in time is dropped rather than deferred.

So the scans are triggered from Railway instead.

Three Railway cron services, all pointed at this repository, all with:

```
Root directory   backend
Build            pip install -r requirements.txt
```

| Service | Start command | Cron (UTC) |
| --- | --- | --- |
| `trigger-scan` | `python scripts/trigger_workflow.py unusual-scan.yml` | `13 14-21 * * 1-5` |
| `trigger-desk` | `python scripts/trigger_workflow.py signal-desk.yml` | `7,37 13-21 * * 1-5` |
| `trigger-close` | `python scripts/trigger_workflow.py unusual-scan.yml --sweep-attention` | `43 21 * * 1-5` |

`--sweep-attention` is the difference that matters. The sweep paces itself
around Yahoo's limiter, takes about nine minutes, and the archive keeps one
reading per trading day — so it belongs on the post-close run and nowhere else.
Without the flag the hourly runs publish prices and leave the archive alone.

All three need `GITHUB_DISPATCH_TOKEN` — a fine-grained PAT scoped to
**Actions: write on `Princ3k/quantimental`** and nothing else. Do not put it on
the API service: nothing there dispatches anything, and a repository-write
token has no business in a public-facing process.

`trigger-close` is the one to watch. It is the only run that writes to the
attention archive, and that reading cannot be backfilled from anywhere at any
price — a day missed is gone.

The cron blocks in `.github/workflows/*.yml` are left in place. They cost
nothing while dormant, and if GitHub ever starts honouring them the trigger
script skips any dispatch that would land on a run already in flight.

