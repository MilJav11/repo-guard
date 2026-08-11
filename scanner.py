import sys
import json
import subprocess
import pathlib
import re
from typing import List, Dict, Any
from rules import RULES, EXCLUDED_DIRS, EXCLUDED_EXTENSIONS, EXCLUDED_FILES, TESTING_KEYWORDS
from findings import Finding, Severity

# ---------------------------------------------------------------------------
# Allowlist validation limits
# ---------------------------------------------------------------------------

MAX_ALLOWLIST_SIZE = 64 * 1024   # 64 KiB
MAX_PATTERN_LENGTH = 256


# ---------------------------------------------------------------------------
# ReDoS detection
# ---------------------------------------------------------------------------

def _detect_nested_quantifier(pattern: str) -> bool:
    r"""Conservative pure-Python detection of ReDoS-prone nested quantifiers.

    Strategy
    --------
    1.  Strip backslash-escaped characters (so ``\)``, ``\+`` etc. are
        treated as literals, not regex syntax).
    2.  Strip character classes ``[...]`` so that ``+`` / ``*`` inside
        brackets are ignored.
    3.  Find every ``)`` immediately followed by ``+`` or ``*``.
    4.  Walk backwards to locate the matching ``(``, then inspect the body
        between them.  If the body contains ``+`` or ``*`` we have a nested
        quantifier — the hallmark of exponential backtracking.

    Returns ``True`` when a dangerous nested quantifier is detected.
    """
    # Step 1 & 2 — replace escapes with placeholder, strip character classes
    cleaned = re.sub(r"\\.", "X", pattern)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)

    # Step 3 — every `)` followed by `+` or `*`
    for m in re.finditer(r"\)[\+\*]", cleaned):
        close_pos = m.start()
        # Step 4 — find matching `(`
        depth = 0
        open_pos = None
        for i in range(close_pos, -1, -1):
            ch = cleaned[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                depth -= 1
                if depth == 0:
                    open_pos = i
                    break
        if open_pos is None:
            continue
        body = cleaned[open_pos + 1 : close_pos]
        if "+" in body or "*" in body:
            return True
    return False

class ScannerError(Exception):
    """Raised when an internal error occurs (e.g., git fails)."""
    pass

def _run_git_command(args: List[str]) -> bytes:
    try:
        result = subprocess.run(args, capture_output=True, check=True, timeout=30)
        return result.stdout
    except subprocess.TimeoutExpired:
        raise ScannerError(f"Git command timed out after 30s: {' '.join(args)}")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode("utf-8", errors="replace").strip()
        raise ScannerError(f"Git command failed: {' '.join(args)}\n{error_msg}")
    except FileNotFoundError:
        raise ScannerError("Git is not installed or not available in PATH.")

def load_allowlist() -> Dict[str, Any]:
    allowlist_path = pathlib.Path("allowlist.json")
    if not allowlist_path.exists():
        return {"paths": [], "patterns": []}

    # 1. File-size guard -------------------------------------------------
    try:
        fsize = allowlist_path.stat().st_size
    except OSError as e:
        raise ScannerError(f"Cannot read allowlist.json: {e}")
    if fsize > MAX_ALLOWLIST_SIZE:
        raise ScannerError(
            f"allowlist.json is {fsize} bytes, exceeds maximum of "
            f"{MAX_ALLOWLIST_SIZE} bytes (64 KiB)."
        )

    # 2. Parse JSON ------------------------------------------------------
    try:
        with open(allowlist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ScannerError(f"Failed to parse allowlist.json: {e}")
    except Exception as e:
        raise ScannerError(f"Failed to read allowlist.json: {e}")

    # 3. Structure validation --------------------------------------------
    if not isinstance(data, dict):
        raise ScannerError(
            "allowlist.json must be a JSON object with 'paths' and 'patterns' keys."
        )

    if "paths" not in data or "patterns" not in data:
        raise ScannerError(
            "allowlist.json must contain both 'paths' and 'patterns' keys."
        )

    paths = data["paths"]
    patterns = data["patterns"]

    if not isinstance(paths, list):
        raise ScannerError("allowlist.json: 'paths' must be a list.")
    if not isinstance(patterns, list):
        raise ScannerError("allowlist.json: 'patterns' must be a list.")

    for i, p in enumerate(paths):
        if not isinstance(p, str):
            raise ScannerError(
                f"allowlist.json: 'paths[{i}]' must be a string, "
                f"got {type(p).__name__}."
            )

    for i, p in enumerate(patterns):
        if not isinstance(p, str):
            raise ScannerError(
                f"allowlist.json: 'patterns[{i}]' must be a string, "
                f"got {type(p).__name__}."
            )

        # 4. Pattern-length guard ----------------------------------------
        if len(p) > MAX_PATTERN_LENGTH:
            raise ScannerError(
                f"allowlist.json: 'patterns[{i}]' is {len(p)} characters, "
                f"exceeds maximum of {MAX_PATTERN_LENGTH}."
            )

        # 5. ReDoS guard -------------------------------------------------
        if _detect_nested_quantifier(p):
            raise ScannerError(
                f"allowlist.json: 'patterns[{i}]' contains a dangerous "
                f"nested quantifier and is rejected to prevent ReDoS attacks."
            )

        # 6. Regex-syntax check ------------------------------------------
        try:
            re.compile(p)
        except re.error as e:
            raise ScannerError(
                f"allowlist.json: 'patterns[{i}]' is not a valid regex: {e}"
            )

    return data

def is_excluded(filepath: str, allowlist_paths: List[str]) -> bool:
    path = pathlib.Path(filepath)
    
    if path.name in EXCLUDED_FILES:
        return True
    
    if path.suffix in EXCLUDED_EXTENSIONS:
        return True
    
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
        
    for allowed_path in allowlist_paths:
        if filepath.startswith(allowed_path):
            return True
            
    return False

def get_staged_files() -> List[str]:
    raw = _run_git_command(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"])
    if not raw:
        return []
    return [f for f in raw.decode("utf-8", errors="replace").split('\x00') if f]

def get_file_size(filepath: str) -> int:
    try:
        raw = _run_git_command(["git", "cat-file", "-s", f":{filepath}"])
        return int(raw.decode("utf-8", errors="replace").strip())
    except ScannerError:
        return 0

def get_file_content(filepath: str) -> bytes:
    return _run_git_command(["git", "show", f":{filepath}"])

def scan_repository() -> List[Finding]:
    findings = []
    
    allowlist = load_allowlist()
    allowlist_paths = allowlist.get("paths", [])
    raw_patterns = allowlist.get("patterns", [])
    
    compiled_allowlist = [re.compile(p) for p in raw_patterns]
    
    try:
        staged_files = get_staged_files()
    except ScannerError as e:
        raise e
        
    for filepath in staged_files:
        path_obj = pathlib.Path(filepath)
        
        if path_obj.name == ".env":
            sys.stderr.write("WARNING: .env file staged for commit. Verify this is intentional.\n")
            
        if is_excluded(filepath, allowlist_paths):
            continue
            
        size = get_file_size(filepath)
        if size > 1024 * 1024:
            continue
            
        raw_content = get_file_content(filepath)
        if b'\x00' in raw_content:
            continue
            
        content = raw_content.decode("utf-8", errors="replace")
        
        for line_num, line in enumerate(content.splitlines(), start=1):
            if any(p.search(line) for p in compiled_allowlist):
                continue

            for rule in RULES:
                for match in rule.pattern.finditer(line):
                    matched_str = match.group()
                    
                    severity = rule.severity
                    if any(kw in matched_str.lower() for kw in TESTING_KEYWORDS):
                        severity = Severity.LOW
                    
                    findings.append(Finding(
                        rule_name=rule.name,
                        severity=severity,
                        description=rule.description,
                        file_path=filepath,
                        line_number=line_num
                    ))
                    
    return findings
