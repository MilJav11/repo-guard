# repo-guard

One accidental commit can leak a real API key.
repo-guard blocks secrets before they ever reach GitHub.

A lightweight local pre-commit hook that scans staged Git content to prevent
accidental secret leaks.

### Security Disclaimer

**repo-guard protects FUTURE commits only.** It is a strictly deterministic,
offline local developer safety net. It does **not** scan Git history, remote
repositories, or replace enterprise SOC products and server-side secret
scanning (GitHub Advanced Security, Gitleaks, etc.). It detects known and
common patterns only — it cannot detect every possible secret format.

## Why repo-guard Exists

Modern AI coding assistants frequently generate:
- Real API keys
- Copied environment variables
- Unsafe example configs
- Accidentally staged secrets

Developers usually notice secrets after they already reached GitHub. `repo-guard`
exists to stop accidental leaks before the commit succeeds.

## Demo

A real staged OpenAI API key being blocked before commit.

https://github.com/user-attachments/assets/dd57abc2-b434-4cdd-b640-99add1edd382

## Installation

You can install `repo-guard` globally directly from GitHub:

```bash
pip install git+https://github.com/MilJav11/repo-guard.git
```

Then, navigate to any of your local Git repositories and activate the guard:

```bash
repo-guard install-hook
# run inside your target Git repository
```

## Quick Test

```bash
echo 'OPENAI_API_KEY="sk-123..."' > temp_test_file.py
git add temp_test_file.py
git commit -m "test"
```

Expected result:

```plaintext
[CRITICAL] OpenAI API key detected
File: temp_test_file.py
Line: 1

[CRITICAL] Blocking findings detected. Commit blocked.
```

Clean up afterwards:

**Windows (PowerShell):**

```powershell
git restore --staged temp_test_file.py
Remove-Item temp_test_file.py
```

**macOS / Linux (Bash):**

```bash
git restore --staged temp_test_file.py && rm temp_test_file.py
```

## How It Works

* **Index-Aware (Staged Only)**: repo-guard scans the staged Git index
  (`git diff --cached`), not the working tree on disk. Unstaged changes are
  never treated as committed content.
* **Fast**: The normal pre-commit path is designed to be lightweight — it
  skips binaries, ignores files >1 MB, and scans only staged content.
  Actual time depends on repository size, staged content, and Git
  performance.
* **Offline-First**: The scanner itself performs local scanning and does
  not require API calls, telemetry, or tracking.
* **Deterministic**: Uses transparent regex-based detection with no AI, ML,
  or hidden heuristics.
* **Fail-Safe**: Internal scanner failures, Git command errors, and Git
  subprocess timeouts (30 second limit) all return explicit non-zero exit
  codes — the commit is blocked by design (fail-closed).
* **DX Friendly**: Prints a warning when `.env` files are staged, and
  downgrades findings that contain known testing keywords (e.g. `test`,
  `example`, `your-key-here`) to LOW severity.

## Supported Providers (Blocking)

* OpenAI
* Anthropic
* Google Gemini
* Groq
* GitHub
* AWS
* Stripe Live

## Allowlist Configuration

repo-guard supports an optional `allowlist.json` file placed in the repository
root.

**Default behaviour (no file):**

When `allowlist.json` does not exist, the scanner uses an empty allowlist:

```json
{"paths": [], "patterns": []}
```

**Custom allowlist:**

```json
{
  "paths": ["tests/fixtures/"],
  "patterns": [
    "^tests/.*",
    "\\.env\\.example$",
    "[a-f0-9]{32}"
  ]
}
```

- `paths` — list of path prefixes; staged files whose path starts with any
  entry are skipped.
- `patterns` — list of Python regex patterns; lines matching any pattern are
  excluded from secret detection.

**Validation rules:**

| Rule | Limit |
|---|---|
| Maximum file size | 64 KiB |
| Top-level JSON structure | object with `"paths"` and `"patterns"` keys |
| Key types | both values must be lists of strings |
| Maximum pattern length | 256 characters |
| Regex validity | invalid regex syntax → commit blocked |
| ReDoS defence | selected dangerous nested-quantifier patterns (e.g. `(a+)+b`) are rejected |

**Any validation failure raises a configuration error (exit code 2) and blocks
the commit — the scanner fails closed.**

### ReDoS protection scope

The scanner applies a deterministic static check that detects nested quantifier
patterns such as `(a+)+b` and `(x|x+)+y`. This is a conservative defence
against a known class of catastrophic backtracking attacks, **not** a complete
ReDoS solution. Keep custom patterns short and simple.

## Example Output

When a secret is detected during `git commit`:

```plaintext
[CRITICAL] OpenAI API key detected
File: example.py
Line: 18

[CRITICAL] Blocking findings detected. Commit blocked.
```

## Exit Codes

| Code | Meaning |
|---|---|
| **0** | No blocking findings (Success) |
| **1** | Blocking secret detected (Commit blocked) |
| **2** | Scanner, Git, or configuration failure (Fail-closed block) |

## Testing

Run the test suite from the repository root:

```bash
python -m pytest tests/ -v
```

The suite currently contains **22 tests** covering regex rules, staged-content
scanning, UTF-8 handling, and allowlist validation (including size limits,
structure checks, and ReDoS detection).

## Design Philosophy

repo-guard intentionally avoids:
* AI classification
* Entropy scoring
* Fuzzy matching

The goal is predictable behavior, fast execution, and low false positives
during normal developer workflows. Security tools should be transparent,
deterministic, and fast — not black boxes.

## Performance Philosophy

repo-guard is designed so the normal pre-commit path is lightweight and fast.
Actual time depends on repository size, staged content, and Git performance.

Developers frequently bypass slow hooks using `git commit --no-verify`.
The scanner intentionally prioritizes deterministic regex matching,
staged-file-only scanning, and safe binary skipping to ensure you never feel
the need to bypass your safety net.

## Why not Gitleaks?

repo-guard intentionally optimizes for:
- ultra-fast local execution
- staged-only validation
- low false positives
- zero configuration
- simple deterministic behavior

It is designed as a lightweight developer guardrail, not as a full enterprise
secret scanning platform.

## Limitations

repo-guard intentionally does **not**:
* Scan Git history
* Scan remote repositories
* Detect unknown or unpatterned secret formats
* Perform multi-line contextual heuristic analysis
* Replace enterprise-grade server-side secret scanning solutions
* Provide complete ReDoS protection (deterministic static defence only)
* Guarantee zero false positives or zero false negatives

It is strictly optimized for fast, local, offline protection against common
accidental exposures.
