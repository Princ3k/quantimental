# Deployment check

A read-only verification of what the scans published. Nothing here changes or
pushes anything; it exists so a scheduled agent — which starts with no context —
can confirm the machinery worked without being handed a wall of prose.

## Background

A private archive records how much news coverage each S&P 500 company gets, one
reading per trading day. It needs 20 sessions before it can call any day's
coverage unusual. The published snapshot carries the *count* of sessions as
`archive_days` — never the readings — because that count is what distinguishes
"coverage was ordinary" from "there is not enough history to say".

`archive_days` was added on 2026-09-15 and first appears after a post-close
sweep, which runs at 21:43 UTC on weekdays.

## What to check

**1. The published snapshot**

```bash
curl -s https://raw.githubusercontent.com/Princ3k/quantimental/main/public/snapshot.json
```

Report `as_of`, `generated_at`, `archive_days`, `archive_days_needed`, how many
entries in `stocks` carry a `v` key (a coverage reading) and how many carry an
`f` key (an SEC filing).

Expect `as_of` to be the most recent trading day, `archive_days` to have grown
by one since the previous trading day, `archive_days_needed` to be 20, and `v`
to be present on all 503.

**2. The operations page**

```bash
curl -s https://www.thequantimental.com/ops
```

Strip the HTML tags and read the *Attention archive* section. It should name a
session count and how many more are needed — not "not reported by the last
scan", which means the sweep did not publish `archive_days`.

**3. The sweep itself**

```bash
curl -s 'https://api.github.com/repos/Princ3k/quantimental/actions/workflows/unusual-scan.yml/runs?per_page=10'
```

Find the run nearest 21:43 UTC on the day being checked, then fetch
`/actions/runs/<id>/jobs` and confirm the step **Scan, and measure attention**
succeeded. A run where that step is `skipped` was an hourly price scan, not the
sweep — the sweep is the only one that writes to the archive, and its reading
cannot be backfilled from anywhere at any price.

## Reporting

State each result plainly. Flag anything that differs from the expectation,
with the actual value beside it. If `archive_days` is still absent, say so and
check whether any sweep ran at all that day.
