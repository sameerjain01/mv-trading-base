"""Push files to GitHub via the REST API.

Reads GITHUB_PAT and GITHUB_REPO from the environment — same pattern as
send_alert() reads SMTP credentials. Silent on failure; never raises, never
blocks the trading pipeline.

Usage:
    from trading_base.journal.github_push import push_file

    push_file(
        file_path="my-system/journal/2026-06-07-paper.md",
        content=report_text,
        commit_message="journal: eod 2026-06-07",
    )

Environment variables:
    GITHUB_PAT   — fine-grained personal access token, contents:write on target repo
    GITHUB_REPO  — owner/repo (e.g. "sameerjain01/mv-opt-one"); falls back to
                   the per-project default passed as default_repo
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


def push_file(
    file_path: str,
    content: str | bytes,
    commit_message: str,
    *,
    default_repo: str = "",
) -> bool:
    """Create or update a file in the GitHub repo.

    Returns True on success, False if GITHUB_PAT not set or request fails.
    """
    pat = os.environ.get("GITHUB_PAT", "")
    if not pat:
        logger.debug("GITHUB_PAT not set — skipping GitHub push")
        return False

    repo = os.environ.get("GITHUB_REPO", default_repo)
    if not repo:
        logger.debug("GITHUB_REPO not set and no default_repo — skipping GitHub push")
        return False

    url = f"{_GITHUB_API}/repos/{repo}/contents/{file_path}"

    if isinstance(content, str):
        content = content.encode("utf-8")
    encoded = base64.b64encode(content).decode("ascii")

    sha = _get_file_sha(url, pat)

    payload: dict = {"message": commit_message, "content": encoded}
    if sha:
        payload["sha"] = sha

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="PUT",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.getcode()

        if status in (200, 201):
            logger.info("pushed to GitHub: %s", file_path)
            return True

        logger.warning("GitHub push returned status %s for %s", status, file_path)
        return False

    except urllib.error.HTTPError as exc:
        logger.warning("GitHub push HTTP error %s for %s: %s", exc.code, file_path, exc.reason)
        return False
    except Exception as exc:
        logger.warning("GitHub push failed for %s: %s", file_path, exc)
        return False


def _get_file_sha(url: str, pat: str) -> str | None:
    """Return the current blob SHA (required by GitHub API to update an existing file)."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
        return body.get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        logger.debug("SHA fetch error %s: %s", exc.code, exc.reason)
        return None
    except Exception as exc:
        logger.debug("SHA fetch failed: %s", exc)
        return None
