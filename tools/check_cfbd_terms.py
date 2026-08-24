#!/usr/bin/env python3
"""Fail closed if the published CFBD Terms effective date changes."""

from __future__ import annotations

import argparse
import html
import re
import urllib.request


TERMS_URL = "https://collegefootballdata.com/terms"


def fetch_effective_date(url: str = TERMS_URL) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mapq-quarterback-metrics/1.1 terms-check"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        markup = response.read().decode("utf-8", errors="replace")
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = re.sub(r"\s+", " ", text)
    match = re.search(
        r"Effective date:\s*([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        text,
    )
    if not match:
        raise RuntimeError("could not identify the CFBD Terms effective date")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Confirm that CFBD's published Terms effective date is unchanged."
    )
    parser.add_argument("--expected", required=True, help="Expected effective date")
    args = parser.parse_args(argv)
    observed = fetch_effective_date()
    if observed != args.expected:
        raise RuntimeError(
            "CFBD Terms changed: "
            f"expected effective date {args.expected!r}, observed {observed!r}. "
            "Review the current terms before refreshing a public release."
        )
    print(f"CFBD Terms effective date confirmed: {observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
