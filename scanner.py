import sys
import json
import subprocess
import pathlib
import re
from typing import List, Dict, Any
from rules import RULES, EXCLUDED_DIRS, EXCLUDED_EXTENSIONS, EXCLUDED_FILES, TESTING_KEYWORDS
from findings import Finding, Severity

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
    
    try:
        with open(allowlist_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise ScannerError(f"Failed to parse allowlist.json: {e}")

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
    
    compiled_allowlist = []
    for p in raw_patterns:
        try:
            compiled_allowlist.append(re.compile(p))
        except re.error as e:
            sys.stderr.write(f"WARNING: Invalid regex in allowlist.json '{p}': {e}\n")
    
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
