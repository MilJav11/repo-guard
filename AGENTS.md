# repo-guard – Agent Guide

## 1. Project overview

repo-guard is a Python CLI and Git pre-commit secret scanner. It scans **staged Git
content only** (not the working tree) to block commits that contain known secret
patterns (API keys, tokens, credentials).

- **CLI entry point:** `guard.py` (Click-based, `repo-guard` command).
- **Git hook:** `git_hooks.py` installs a `pre-commit` hook that runs the scanner.
- **Scanner engine:** `scanner.py` reads the Git index (`git diff --cached`),
  applies detection rules, and reports findings.
- **Detection rules:** `rules.py` contains pre-compiled deterministic regex patterns
  for OpenAI, Anthropic, Google Gemini, Groq, GitHub, AWS, and Stripe Live keys,
  plus a generic password-detection rule.

There is **no frontend, no database, and no API server** — the tool runs entirely
offline on the local filesystem.

## 2. Repository structure

| Path | Responsibility |
|---|---|
| `guard.py` | CLI entry point (`install-hook` and `scan` subcommands) |
| `scanner.py` | Core scanning engine, allowlist loading/validation, ReDoS detection |
| `rules.py` | Secret-detection rules (`RULES`), exclusion sets, testing keywords |
| `git_hooks.py` | Pre-commit hook installation (backup, idempotency, marker-based) |
| `findings.py` | `Severity` enum and `Finding` dataclass with `format_terminal()` |
| `tests/test_scanner.py` | Unit tests for scanner, allowlist validation, ReDoS, UTF-8 handling |
| `tests/test_rules.py` | Unit tests for detection regexes (positive/negative matches) |
| `tests/e2e_test.sh` | End-to-end bash test script (6 scenarios + hook safety) |
| `.github/workflows/tests.yml` | CI: Ubuntu & Windows, Python 3.11–3.14 |
| `.gitignore` | Ignores `__pycache__/`, `.venv/`, `dist/`, `.env`, `.pytest_cache/` |

## 3. Supported environment

- **Python:** `>=3.11` (exact value from `pyproject.toml`)
- **Runtime dependency:** `click>=8.1.0` (from `requirements.txt` and `pyproject.toml`)
- **CI matrix:** Python 3.11, 3.12, 3.13, 3.14 on Ubuntu and Windows
- **No frontend, database, or API server.**

## 4. Development commands

Install runtime dependencies:
```bash
pip install -r requirements.txt
```

Install with test dependencies:
```bash
pip install -r requirements.txt
pip install pytest
```

Run the test suite (unit tests only; E2E test requires a Git repo):
```bash
python -m pytest tests/ -v
```

CLI usage (after installation):
```bash
repo-guard install-hook         # install the pre-commit hook
repo-guard scan                 # scan staged files for secrets
```

Run the E2E test (requires bash and a Git installation):
```bash
bash tests/e2e_test.sh
```

There is no command to run GitHub Actions locally; the CI workflow is
`.github/workflows/tests.yml`.

## 5. Project invariants

- **Deterministic detection.** All secret detection uses pre-compiled regex patterns
  in `rules.py`. There is no AI, ML, entropy scoring, or fuzzy matching.
- **Fail-closed.** Any scanner error, Git error, timeout, or configuration error
  produces a non-zero exit code and blocks the commit:
  - Exit `0` — no blocking findings (success).
  - Exit `1` — blocking secret detected (commit blocked).
  - Exit `2` — scanner, Git, or configuration failure (commit blocked).
- **Staged-content only.** The scanner reads `git diff --cached`; unstaged working-tree
  changes are never scanned. Verified by the E2E test Scenario B.
- **CLI compatibility.** The `repo-guard` command exposes `install-hook` and `scan`
  subcommands. Their behavior and exit codes are part of the public contract.
- **Detection rules are stable.** Rules in `RULES` (OpenAI, Anthropic, Gemini, Groq,
  GitHub, AWS, Stripe Live, Generic Password) should not be casually changed — changes
  affect what gets blocked for every user.
- **No new runtime dependencies** may be added without explicit approval. The only
  runtime dependency is `click>=8.1.0`.
- **30-second timeout.** All Git subprocess calls have a 30-second timeout; exceeding
  it raises `ScannerError` / `HookError` (fail-closed, exit 2).
- **Binary and oversized files skipped.** Files with null bytes or >1 MB are skipped.
  `.env` files trigger a warning but are still scanned.

## 6. Agent workflow

When modifying this repository, follow these guidelines:

1. **Inspect before editing.** Read the relevant source files, tests, and
   `pyproject.toml` to understand existing conventions.
2. **Present a short plan** before making non-trivial changes.
3. **Make the smallest necessary change.** Prefer surgical edits over rewrites.
4. **Run relevant tests after editing:**
   ```bash
   python -m pytest tests/ -v
   ```
5. **Show `git diff` and `git status --short`** after changes so the user can
   inspect them.
6. **Never commit or push** without explicit user approval.

## 7. Validation checklist

After making changes, verify:

1. Tests pass:
   ```bash
   python -m pytest tests/ -v
   ```
2. No whitespace or diff issues:
   ```bash
   git diff --check
   ```
3. Only intended files were changed:
   ```bash
   git status --short
   ```
