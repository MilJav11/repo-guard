import sys
import subprocess
import pathlib
import datetime
import stat
import os

HOOK_START_MARKER = "# repo-guard hook start"
HOOK_END_MARKER = "# repo-guard hook end"

HOOK_SCRIPT = """
#!/bin/sh
# .git/hooks/ is 2 levels deep, so ../../ resolves to the repo root
SCRIPT_DIR="$(cd "$(dirname "$0")/../../" && pwd)"
exec python "$SCRIPT_DIR/guard.py" "$@"
"""

class HookError(Exception):
    """Raised when an error occurs during hook installation."""
    pass

def _get_git_root() -> pathlib.Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            text=True
        )
        return pathlib.Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        raise HookError("Could not find git repository root. Are you in a git repository?")
    except FileNotFoundError:
        raise HookError("Git is not installed or not available in PATH.")

def install_hook() -> None:
    repo_root = _get_git_root()
    hooks_dir = repo_root / ".git" / "hooks"
    
    if not hooks_dir.exists():
        hooks_dir.mkdir(parents=True, exist_ok=True)
        
    hook_path = hooks_dir / "pre-commit"
    
    file_exists = hook_path.exists()
    if file_exists:
        content = hook_path.read_text(encoding="utf-8")
        if HOOK_START_MARKER in content:
            sys.stdout.write("repo-guard hook is already installed.\n")
            return
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = hook_path.with_name(f"pre-commit.bak.{timestamp}")
        backup_path.write_text(content, encoding="utf-8")
        sys.stdout.write(f"Backed up existing pre-commit hook to {backup_path.name}\n")

    clean_script = HOOK_SCRIPT.strip()
    
    if file_exists:
        # Append mode: clean internal shebang to avoid duplicates mid-file
        payload = "\n".join([line for line in clean_script.splitlines() if not line.startswith("#!")])
        snippet = f"\n{HOOK_START_MARKER}\n{payload}\n{HOOK_END_MARKER}\n"
        with hook_path.open("a", encoding="utf-8", newline='\n') as f:
            f.write(snippet)
    else:
        # Write mode: SHEBANG MUST BE AT LINE 1, CHARACTER 1
        snippet = f"#!/bin/sh\n\n{HOOK_START_MARKER}\n{clean_script.replace('#!/bin/sh', '').strip()}\n{HOOK_END_MARKER}\n"
        with hook_path.open("w", encoding="utf-8", newline='\n') as f:
            f.write(snippet)
        
    # Make the hook script executable safely
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)
    
    sys.stdout.write("repo-guard pre-commit hook installed successfully.\n")
