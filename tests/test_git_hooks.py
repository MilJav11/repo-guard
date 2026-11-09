import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

# Add root to sys.path for testing
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import git_hooks
from git_hooks import (
    HOOK_END_MARKER,
    HOOK_START_MARKER,
    HookError,
    build_hook_block,
    build_hook_body,
    install_hook,
)

HAS_SH = shutil.which("sh") is not None


class TestHookContent(unittest.TestCase):
    def test_hook_uses_absolute_interpreter_not_bare_python(self):
        body = build_hook_body(sys.executable)
        self.assertIn(git_hooks._quote_sh(sys.executable), body)
        self.assertTrue(os.path.isabs(sys.executable))
        self.assertNotIn("exec python", body)
        self.assertNotIn("guard.py", body)
        self.assertIn('-m guard scan', body)
        self.assertIn(" -P ", body)  # repo must not shadow installed modules

    def test_interpreter_path_is_absolute(self):
        self.assertTrue(os.path.isabs(git_hooks._interpreter_path()))

    def test_block_is_wrapped_in_markers(self):
        block = build_hook_block("/usr/bin/python3")
        self.assertTrue(block.startswith(HOOK_START_MARKER + "\n"))
        self.assertTrue(block.endswith(HOOK_END_MARKER + "\n"))

    @unittest.skipUnless(HAS_SH, "POSIX sh not available")
    def test_quoting_survives_spaces_and_quotes(self):
        weird = "/tmp/my env's/bin/python"
        assignment = build_hook_body(weird).splitlines()[0]
        out = subprocess.run(
            ["sh", "-c", assignment + '\nprintf %s "$REPO_GUARD_PYTHON"'],
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertEqual(out, weird)

    @unittest.skipUnless(HAS_SH, "POSIX sh not available")
    def test_missing_interpreter_fails_closed_with_reinstall_hint(self):
        body = build_hook_body("/nonexistent/dir/python")
        result = subprocess.run(["sh", "-c", body], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Reinstall", result.stderr)
        self.assertIn("Commit blocked", result.stderr)

    @unittest.skipUnless(HAS_SH, "POSIX sh not available")
    def test_missing_package_fails_closed(self):
        # An interpreter that exists but cannot import `guard`: isolate it from
        # every path where repo-guard could be found.
        with tempfile.TemporaryDirectory() as tmp:
            fake = pathlib.Path(tmp) / "python"
            fake.write_text("#!/bin/sh\nexit 1\n")
            fake.chmod(0o755)
            result = subprocess.run(
                ["sh", "-c", build_hook_body(str(fake))], capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Reinstall", result.stderr)


class TestInstallHook(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        subprocess.run(["git", "init", "-q"], check=True)
        self.hook = pathlib.Path(".git") / "hooks" / "pre-commit"

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _install(self) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            install_hook()
        return buf.getvalue()

    def test_fresh_install_writes_absolute_interpreter(self):
        self._install()
        text = self.hook.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertIn(git_hooks._quote_sh(git_hooks._interpreter_path()), text)
        self.assertNotIn("exec python", text)
        self.assertNotIn("guard.py", text)

    def test_second_install_is_idempotent(self):
        self._install()
        before = self.hook.read_text(encoding="utf-8")
        self.assertIn("already installed", self._install())
        self.assertEqual(self.hook.read_text(encoding="utf-8"), before)

    def test_existing_hook_is_appended_and_backed_up(self):
        self.hook.parent.mkdir(parents=True, exist_ok=True)
        self.hook.write_text("#!/bin/sh\necho legacy\n", encoding="utf-8")
        self._install()
        text = self.hook.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh\necho legacy\n"))
        self.assertEqual(text.count(HOOK_START_MARKER), 1)
        self.assertTrue(list(self.hook.parent.glob("pre-commit.bak.*")))

    def test_stale_block_is_refreshed_in_place(self):
        self.hook.parent.mkdir(parents=True, exist_ok=True)
        old = (
            "#!/bin/sh\necho before\n"
            f"{HOOK_START_MARKER}\nexec python \"$SCRIPT_DIR/guard.py\" \"$@\"\n{HOOK_END_MARKER}\n"
            "echo after\n"
        )
        self.hook.write_text(old, encoding="utf-8")
        self.assertIn("updated", self._install())
        text = self.hook.read_text(encoding="utf-8")
        self.assertNotIn("exec python", text)
        self.assertEqual(text.count(HOOK_START_MARKER), 1)
        self.assertIn("echo before", text)
        self.assertIn("echo after", text)
        self.assertIn(git_hooks._quote_sh(git_hooks._interpreter_path()), text)

    def test_start_marker_without_end_marker_is_an_error(self):
        self.hook.parent.mkdir(parents=True, exist_ok=True)
        self.hook.write_text(f"#!/bin/sh\n{HOOK_START_MARKER}\necho x\n", encoding="utf-8")
        with self.assertRaises(HookError):
            self._install()


if __name__ == "__main__":
    unittest.main()
