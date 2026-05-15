"""GitHub REST client for fetching pull requests.

Deliberately minimal:
  - PRs only (issues + commits in a later step).
  - Paginated, with retry-on-rate-limit.
  - Returns raw dicts; caller decides what to persist.

We use the REST API rather than GraphQL because the pagination model is
simpler and the per-PR payload already has what we need for v1.
"""

import time
from typing import Any, Iterator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

API_ROOT = "https://api.github.com"
PER_PAGE = 100 


class RateLimited(Exception):
    """Raised when GitHub signals we've hit the rate limit."""


def _headers(token: str | None) -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _check_rate_limit(resp: httpx.Response) -> None:
    """If we've been told to back off, sleep until reset rather than failing.

    GitHub returns 403 with x-ratelimit-remaining=0 when we're throttled.
    The reset is a unix timestamp in x-ratelimit-reset.
    """
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        reset = int(resp.headers.get("x-ratelimit-reset", "0"))
        sleep_for = max(reset - int(time.time()), 1)
        if sleep_for > 300:
            raise RateLimited(f"rate limited; reset in {sleep_for}s")
        time.sleep(sleep_for + 1)
        raise RateLimited("rate limited; retrying after sleep")


@retry(
    retry=retry_if_exception_type((RateLimited, httpx.TransportError)),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _get(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    resp = client.get(url, params=params)
    _check_rate_limit(resp)
    resp.raise_for_status()
    return resp


def fetch_pulls(
    repo: str,
    token: str | None,
    since: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield PR dicts for a repo, newest-first.

    `since` is an ISO 8601 timestamp; if given, we stop iterating once we
    pass it (GitHub orders pulls by updated_at desc when state=all and
    sort=updated, so this gives us cheap incremental fetches).
    """
    url = f"{API_ROOT}/repos/{repo}/pulls"
    params = {
        "state": "all",
        "sort": "updated",
        "direction": "desc",
        "per_page": PER_PAGE,
    }

    with httpx.Client(headers=_headers(token), timeout=30.0) as client:
        next_url: str | None = url
        next_params: dict[str, Any] | None = params
        while next_url:
            resp = _get(client, next_url, params=next_params)
            for pr in resp.json():
                if since and pr["updated_at"] <= since:
                    return
                yield pr
            # GitHub returns the next page via Link header.
            next_url = resp.links.get("next", {}).get("url")
            next_params = None  # the next link already has params baked in