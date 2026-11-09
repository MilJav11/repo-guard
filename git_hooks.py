import sys
import subprocess
import pathlib
import datetime
import stat
import os

HOOK_START_MARKER = "# repo-guard hook start"
HOOK_END_MARKER = "# repo-guard hook end"

# Python one-liner used by the hook to verify the installed package is still
# importable (find_spec avoids importing click/guard on every commit).
_HOOK_CHECK = (
    "import importlib.util as u, sys; "
    'sys.exit(0 if u.find_spec("guard") and u.find_spec("click") else 1)'
)

class HookError(Exception):
    """Raised when an error occurs during hook installation."""
    pass

def _quote_sh(value: str) -> str:
    """Quote *value* as a single POSIX sh word (safe for spaces and quotes)."""
    return "'" + value.replace("'", "'\\''") + "'"

def _interpreter_path() -> str:
    """Absolute path of the interpreter that is installing the hook."""
    exe = sys.executable
    if not exe:
        raise HookError("Cannot determine the Python interpreter running repo-guard.")
    exe = os.path.abspath(exe)
    if os.name == "nt":
        # The hook is run by Git for Windows' POSIX sh; use forward slashes.
        exe = exe.replace("\\", "/")
    return exe

def build_hook_body(python_path: str) -> str:
    """POSIX sh snippet that runs the installed scanner with *python_path*.

    ``-P`` stops the repository being committed from shadowing the installed
    modules (``guard``, ``scanner``, ``rules``, ...) through ``sys.path``.
    If the interpreter or the package is gone, the hook fails closed.
    """
    return "\n".join([
        f"REPO_GUARD_PYTHON={_quote_sh(python_path)}",
        'if [ ! -x "$REPO_GUARD_PYTHON" ] || '
        f'! "$REPO_GUARD_PYTHON" -P -c {_quote_sh(_HOOK_CHECK)} >/dev/null 2>&1; then',
        '    echo "repo-guard: cannot run the scanner with $REPO_GUARD_PYTHON '
        "(interpreter or repo-guard package is missing). "
        "Reinstall repo-guard and run 'repo-guard install-hook' again. "
        'Commit blocked." >&2',
        "    exit 2",
        "fi",
        '"$REPO_GUARD_PYTHON" -P -m guard scan || exit $?',
    ])

def build_hook_block(python_path: str) -> str:
    """Hook body wrapped in the start/end markers (ends with a newline)."""
    return f"{HOOK_START_MARKER}\n{build_hook_body(python_path)}\n{HOOK_END_MARKER}\n"

def _get_git_root() -> pathlib.Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            text=True,
            timeout=30
        )
        return pathlib.Path(result.stdout.strip())
    except subprocess.TimeoutExpired:
        raise HookError("Git rev-parse timed out after 30s.")
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
    block = build_hook_block(_interpreter_path())

    file_exists = hook_path.exists()
    new_content = None
    if file_exists:
        content = hook_path.read_bytes().decode("utf-8")
        if HOOK_START_MARKER in content:
            start = content.index(HOOK_START_MARKER)
            end = content.find(HOOK_END_MARKER, start)
            if end == -1:
                raise HookError(
                    f"{hook_path} has a repo-guard start marker but no end marker. "
                    "Fix or remove the repo-guard section manually."
                )
            end += len(HOOK_END_MARKER)
            if content[end:end + 1] == "\n":
                end += 1
            if content[start:end] == block:
                sys.stdout.write("repo-guard hook is already installed.\n")
                return
            # Installed by another interpreter / an older repo-guard: refresh in place.
            new_content = content[:start] + block + content[end:]

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = hook_path.with_name(f"pre-commit.bak.{timestamp}")
        backup_path.write_bytes(content.encode("utf-8"))
        sys.stdout.write(f"Backed up existing pre-commit hook to {backup_path.name}\n")

    if new_content is not None:
        with hook_path.open("w", encoding="utf-8", newline='\n') as f:
            f.write(new_content)
        message = "repo-guard pre-commit hook updated successfully.\n"
    elif file_exists:
        # Append mode: existing hook keeps its own shebang
        with hook_path.open("a", encoding="utf-8", newline='\n') as f:
            f.write(f"\n{block}")
        message = "repo-guard pre-commit hook installed successfully.\n"
    else:
        # Write mode: SHEBANG MUST BE AT LINE 1, CHARACTER 1
        with hook_path.open("w", encoding="utf-8", newline='\n') as f:
            f.write(f"#!/bin/sh\n\n{block}")
        message = "repo-guard pre-commit hook installed successfully.\n"

    # Make the hook script executable safely
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    sys.stdout.write(message)
