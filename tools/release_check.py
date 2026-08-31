#!/usr/bin/env python3
"""Fail when a prospective public release contains unsafe or incomplete files."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    ".gitattributes",
    ".github/workflows/weekly-refresh.yml",
    ".gitignore",
    "CHANGELOG.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "docs/DATA_DICTIONARY.md",
    "docs/DATA_RIGHTS.md",
    "docs/METHODOLOGY.md",
    "docs/PLAYER_VERIFICATION.md",
    "docs/readme-hero.png",
    "docs/RELEASE_CHECKLIST.md",
    "docs/SOURCE_EVALUATION.md",
    "docs/VERIFICATION_REPORT_2026-08-24.md",
    "examples/sample_input.json",
    "examples/verification_overrides_template.csv",
    "pyproject.toml",
    "release/README.md",
    "src/mapq/__init__.py",
    "src/mapq/__main__.py",
    "src/mapq/cli.py",
    "src/mapq/cfbd.py",
    "src/mapq/model.py",
    "src/mapq/official.py",
    "src/mapq/release.py",
    "src/mapq/verify.py",
    "sources/official_rosters_2026.csv",
    "tests/test_cfbd.py",
    "tests/test_model.py",
    "tests/test_official.py",
    "tests/test_release.py",
    "tests/test_verify.py",
    "tools/check_cfbd_terms.py",
    "tools/validate_release_data.py",
}
ALLOWED_BINARY_FILES = {
    "docs/readme-hero.png": {
        "signature": b"\x89PNG\r\n\x1a\n",
        "max_bytes": 5 * 1024 * 1024,
    },
}
FORBIDDEN_PATH_PARTS = {"outputs", "work", "scripts", "__pycache__", "node_modules"}
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{30,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic credential assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
    "absolute user path": re.compile(r"/(?:Users|home)/[^/\s]+/"),
    "internal authoring provenance": re.compile(
        r"(?i)\b(?:" + "|".join(("co" + "dex", "chat" + "gpt", "open" + "ai"))
        + r")\b|@" + "oai"
    ),
}
FORBIDDEN_RELEASE_FIELDS = re.compile(
    r"(?i)\b(?:player_id|stats_teams|pass_attempts|completions|pass_yards|"
    r"interceptions|long_pass|sacks|rush_attempts|rush_yards|long_rush|pbp_[a-z_]+|"
    r"provider_player_id|provider_hometown|provider_endpoint|input_hometown)\b"
)
REQUIRED_WORKBOOK_TEXT = (
    "CollegeFootballData.com",
    "MAP-Q",
    "Defense Stress Index",
    "Drive Extension Index",
    "Escape-to-Explosive",
)


def workbook_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            parts = []
            for name in archive.namelist():
                if name.endswith((".xml", ".rels")):
                    parts.append(archive.read(name).decode("utf-8", errors="replace"))
            return "\n".join(parts)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid XLSX archive: {exc}") from exc


def candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def main() -> int:
    files = candidate_files()
    relative = {path.relative_to(ROOT).as_posix() for path in files}
    errors: list[str] = []

    missing = sorted(REQUIRED - relative)
    if missing:
        errors.append("missing required files: " + ", ".join(missing))

    for path in files:
        rel = path.relative_to(ROOT)
        if any(part in FORBIDDEN_PATH_PARTS for part in rel.parts):
            errors.append(f"forbidden release path: {rel}")
            continue
        if path.suffix.lower() == ".xlsx" and rel.parts[0] == "release":
            try:
                text = workbook_text(path)
            except ValueError as exc:
                errors.append(f"{rel}: {exc}")
                continue
            if FORBIDDEN_RELEASE_FIELDS.search(text):
                errors.append(f"private source field found in release workbook: {rel}")
            for required_text in REQUIRED_WORKBOOK_TEXT:
                if required_text not in text:
                    errors.append(f"release workbook missing {required_text!r}: {rel}")
        elif rel.as_posix() in ALLOWED_BINARY_FILES:
            policy = ALLOWED_BINARY_FILES[rel.as_posix()]
            data = path.read_bytes()
            if not data.startswith(policy["signature"]):
                errors.append(f"allowed binary has an invalid file signature: {rel}")
            if len(data) > policy["max_bytes"]:
                errors.append(f"allowed binary exceeds size limit: {rel}")
            continue
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"unexpected binary file: {rel}")
                continue
        if rel.parts[0] == "release" and path.suffix.lower() in {".json", ".csv"}:
            if FORBIDDEN_RELEASE_FIELDS.search(text):
                errors.append(f"private source field found in release artifact: {rel}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{label} pattern found in {rel}")

    sample = json.loads((ROOT / "examples" / "sample_input.json").read_text())
    if sample.get("synthetic") is not True:
        errors.append("example data must be explicitly marked synthetic")
    if len({row["player_id"] for row in sample.get("records", [])}) != len(sample.get("records", [])):
        errors.append("example player_id values are not unique")

    package_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    model_text = (ROOT / "src" / "mapq" / "model.py").read_text()
    model_match = re.search(r'^MODEL_VERSION = "([^"]+)"$', model_text, re.MULTILINE)
    citation_text = (ROOT / "CITATION.cff").read_text()
    citation_match = re.search(r"^version: ([^\s]+)$", citation_text, re.MULTILINE)
    versions = {
        "package": package_version,
        "model": model_match.group(1) if model_match else None,
        "citation": citation_match.group(1) if citation_match else None,
    }
    if len(set(versions.values())) != 1:
        errors.append(f"version mismatch: {versions}")

    if errors:
        print("Release check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Release check passed: {len(files)} publishable files inspected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
