# Changelog

## 1.1.0

- The pre-commit hook now works after `pip` / `pipx` installation: it runs the installed scanner with the absolute interpreter path recorded at install time.
- The hook fails closed: if the interpreter or package is missing, the commit is blocked (exit 2) with a message to reinstall.
- `tests/` and `fixtures/` directories are now scanned.
- Allowlist (`allowlist.json`) is used by this repository for its own synthetic test fixtures.
- The end-to-end test runs in CI.
- README restructured; added a `.pre-commit-hooks.yaml` hook definition for use with pre-commit.

## 1.0.1

- Fix Windows Git Bash compatibility of the end-to-end test.
- Add repository guidance for coding agents.

## 1.0.0

- First stable release: staged-content scanning, allowlist validation with ReDoS defence, Git command timeouts (fail-closed), and a cross-platform CI workflow (Python 3.11–3.14).
