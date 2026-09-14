"""
Fire a GitHub workflow from a clock we control.

GitHub's `schedule` trigger never ran for this repository. Not once, across two
cron configurations and a schedule that sat unchanged for thirty-five hours —
while push and workflow_dispatch worked every single time. The difference is
that those are events somebody sends, and `schedule` is a queue GitHub sweeps
on a best-effort basis: their own documentation says a run that cannot be
started in time is dropped rather than deferred.

So this does what the clicking does. `workflow_dispatch` is the same mechanism
that has succeeded on every manual run; all that was missing was something to
press the button on time. Railway already runs a container here around the
clock, which makes it a more reliable timer than the one we were relying on.

The token is a fine-grained PAT with Actions: write on this repository and
nothing else. That is the whole blast radius if it ever leaks: somebody can
run the scan. It deliberately cannot read code, write contents, or reach the
private archive.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from typing import Any, Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("trigger")

API = "https://api.github.com"
DEFAULT_REPO = "Princ3k/quantimental"
DEFAULT_REF = "main"
TIMEOUT_SECONDS = 30.0

# Statuses that mean a run is already under way. Dispatching over one of these
# would queue a second copy behind it — the workflow's concurrency group keeps
# that from overlapping, but it still spends a Yahoo sweep to publish the same
# numbers twice.
ACTIVE = ("queued", "in_progress", "waiting", "requested", "pending")


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def already_running(client: httpx.Client, repo: str, workflow: str) -> bool:
    """Whether this workflow has a run in flight."""
    try:
        response = client.get(f"{API}/repos/{repo}/actions/workflows/{workflow}/runs?per_page=5")
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
    except Exception as exc:  # noqa: BLE001
        # Not being able to check is not a reason to skip. A duplicate run is
        # cheap; a silently skipped one leaves the site stale.
        logger.warning("Could not check for running dispatches (%s); dispatching anyway.", exc)
        return False

    for run in runs:
        if run.get("status") in ACTIVE:
            logger.info("A run is already %s (started %s).", run["status"], run["created_at"])
            return True
    return False


def dispatch(
    repo: str,
    workflow: str,
    ref: str,
    token: str,
    inputs: Optional[dict[str, str]] = None,
) -> int:
    with httpx.Client(headers=_headers(token), timeout=TIMEOUT_SECONDS) as client:
        if already_running(client, repo, workflow):
            logger.info("Nothing to do.")
            return 0

        body: dict[str, Any] = {"ref": ref}
        if inputs:
            body["inputs"] = inputs

        response = client.post(
            f"{API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
            json=body,
        )

        if response.status_code == 204:
            logger.info(
                "Dispatched %s on %s%s.", workflow, ref,
                f" with {inputs}" if inputs else "",
            )
            return 0

        # 404 here is usually the token rather than the workflow: a fine-grained
        # PAT without Actions: write sees the endpoint as missing rather than
        # forbidden, which is a confusing way to be told the scope is wrong.
        if response.status_code == 404:
            logger.error(
                "GitHub returned 404 for %s. Either the workflow file name is wrong, "
                "or the token lacks Actions: write on %s.", workflow, repo,
            )
        else:
            logger.error("Dispatch failed: HTTP %s %s", response.status_code, response.text[:200])
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch a GitHub Actions workflow.")
    parser.add_argument(
        "workflow",
        nargs="?",
        default="unusual-scan.yml",
        help="Workflow file name, e.g. unusual-scan.yml",
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO))
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF_NAME", DEFAULT_REF))
    parser.add_argument(
        "--sweep-attention",
        action="store_true",
        help=(
            "Ask the scan to measure news coverage and archive it. Belongs on "
            "the post-close run only: it takes about nine minutes and the "
            "archive keeps one reading per trading day."
        ),
    )
    args = parser.parse_args()

    token = (os.environ.get("GITHUB_DISPATCH_TOKEN") or "").strip()
    if not token:
        logger.error(
            "GITHUB_DISPATCH_TOKEN is not set. It needs a fine-grained PAT with "
            "Actions: write on %s and nothing else.", args.repo,
        )
        return 1

    inputs = {"sweep_attention": "true"} if args.sweep_attention else None
    return dispatch(args.repo, args.workflow, args.ref, token, inputs)


if __name__ == "__main__":
    sys.exit(main())
