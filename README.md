# repo-guard

A lightweight, lightning-fast local pre-commit hook designed to prevent accidental secret leaks in AI-generated repositories.

### ⚠️ Security Disclaimer
**repo-guard protects FUTURE commits only.**
This is a strictly deterministic, offline local developer safety net. It does **NOT** scan git history, remote repositories, or replace enterprise SOC products and server-side secret scanning.

## Why repo-guard Exists

Modern AI coding assistants frequently generate:
- Real API keys
- Copied environment variables
- Unsafe example configs
- Accidentally staged secrets

Developers often notice these issues too late — after pushing to GitHub. `repo-guard` exists to stop accidental leaks before the commit succeeds.

## Installation

Clone the repository and install it locally in editable mode:
```bash
git clone https://github.com/your-username/repo-guard.git
cd repo-guard
pip install -e .
```
Now you can use the tool globally within your local repository:

```bash
repo-guard install-hook
```

## How It Works

* **Index-Aware (Staged Only)**: Unlike many naive scanners, repo-guard validates the staged git index itself, not the working tree on disk. This prevents false assumptions when staged content differs from local files.
* **Fast**: Skips binaries, ignores files >1MB, and executes in milliseconds to keep your workflow fluid.
* **Offline-First**: Everything happens locally. No API calls, no telemetry, no tracking.
* **Deterministic**: Uses transparent regex-based detection with no AI, ML, or hidden heuristics.
* **Fail-Safe**: Internal scanner failures or git command errors return explicit non-zero exit codes instead of silently allowing commits (fail-closed design).
* **DX Focused**: Warning downgrades for test files and .env files to prevent blocking you during normal workflows.

## Supported Providers (Blocking)

* OpenAI
* Anthropic
* Google Gemini
* Groq
* GitHub
* AWS
* Stripe Live

## Example Output

When a secret is detected during git commit:

```plaintext
[CRITICAL] OpenAI API key detected
File: config.py
Line: 18

[CRITICAL] Blocking findings detected. Commit blocked.
```

## Exit Codes

| Code | Meaning |
|---|---|
| **0** | No blocking findings (Success / Warning allowed) |
| **1** | Blocking secret detected (Commit blocked) |
| **2** | Internal scanner or Git failure (Fail-closed block) |

## Design Philosophy

repo-guard intentionally avoids:
* AI classification
* Entropy scoring
* Fuzzy matching

The goal is predictable behavior, fast execution, and zero false positives during normal developer workflows. Security tools should be transparent, deterministic, and fast – not black boxes.

## Performance Philosophy

repo-guard is designed to execute in under one second during normal commits.

Why? Because developers frequently bypass slow hooks using `git commit --no-verify`.
The scanner intentionally prioritizes deterministic regex matching, staged-file-only scanning, and safe binary skipping to ensure you never feel the need to bypass your safety net.

## Limitations

repo-guard intentionally does NOT:
* Scan git history
* Scan remote repositories
* Detect unknown or unpatterned secret formats
* Perform multi-line contextual heuristic analysis
* Replace enterprise-grade server-side secret scanning solutions

It is strictly optimized for fast, local, offline protection against common accidental exposures.
