import sys
import json
import os
import pathlib
import re
import tempfile
import unittest
from unittest.mock import patch

# Add root to sys.path for testing
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from scanner import is_excluded, scan_repository, load_allowlist, ScannerError
from findings import Severity

class TestScanner(unittest.TestCase):
    
    def test_is_excluded(self):
        allowlist = ["tests/fixtures/"]
        
        # Excluded dirs
        self.assertTrue(is_excluded("node_modules/index.js", allowlist))
        self.assertTrue(is_excluded("backend/venv/bin/activate", allowlist))
        
        # Excluded extensions
        self.assertTrue(is_excluded("users.db", allowlist))
        self.assertTrue(is_excluded("app.pyc", allowlist))
        
        # Excluded files
        self.assertTrue(is_excluded("frontend/package-lock.json", allowlist))
        
        # Allowlist paths
        self.assertTrue(is_excluded("tests/fixtures/secret.txt", allowlist))
        
        # Should not be excluded
        self.assertFalse(is_excluded("src/main.py", allowlist))
        self.assertFalse(is_excluded("config.py", allowlist))

    @patch("scanner._run_git_command")
    @patch("scanner.load_allowlist")
    def test_scan_repository(self, mock_load_allowlist, mock_run_git_command):
        mock_load_allowlist.return_value = {"paths": [], "patterns": []}
        
        def mock_git_command_effect(args):
            if args[1] == "diff":
                return b"config.py\x00test_config.py\x00image.png\x00"
            elif args[1] == "cat-file":
                return b"1024" # 1KB
            elif args[1] == "show":
                filename = args[2][1:]
                if filename == "config.py":
                    return b'API_KEY = "sk-1234567890abcdefghij1234567890"'
                elif filename == "test_config.py":
                    return b'TEST_KEY = "sk-test-1234567890abcdefghij123456"'
                elif filename == "image.png":
                    return b'\x89PNG\r\n\x1a\n\x00\x00\x00'
            return b""

        mock_run_git_command.side_effect = mock_git_command_effect
        
        findings = scan_repository()
        
        # Should skip image.png (binary detection due to \x00)
        # Should flag config.py as CRITICAL
        # Should flag test_config.py as LOW (downgrade due to 'test' keyword)
        
        self.assertEqual(len(findings), 2)
        
        config_finding = next((f for f in findings if f.file_path == "config.py"), None)
        self.assertIsNotNone(config_finding)
        self.assertEqual(config_finding.severity, Severity.CRITICAL)
        
        test_finding = next((f for f in findings if f.file_path == "test_config.py"), None)
        self.assertIsNotNone(test_finding)
        self.assertEqual(test_finding.severity, Severity.LOW)

    @patch("scanner._run_git_command")
    @patch("scanner.load_allowlist")
    def test_invalid_utf8_handling(self, mock_load_allowlist, mock_run_git_command):
        mock_load_allowlist.return_value = {"paths": [], "patterns": []}
        
        def mock_git_command_effect(args):
            if args[1] == "diff":
                return b"bad_file.txt\x00"
            elif args[1] == "cat-file":
                return b"1024"
            elif args[1] == "show":
                # Return b'\xff\xfe' which is invalid UTF-8 and normally raises UnicodeDecodeError
                return b'API_KEY="sk-1234567890abcdefghij1234567890"\nInvalid \xff\xfe bytes'
            return b""
            
        mock_run_git_command.side_effect = mock_git_command_effect
        
        # Should NOT raise UnicodeDecodeError and gracefully scan the readable parts
        findings = scan_repository()
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file_path, "bad_file.txt")
        self.assertEqual(findings[0].severity, Severity.CRITICAL)


class TestAllowlistValidation(unittest.TestCase):
    """Tests for allowlist.json validation logic.

    Covers missing-file defaults, invalid JSON, structure validation,
    type checking, size limits, pattern-length limits, ReDoS detection,
    and end-to-end allowlist pattern matching.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def setUp(self):
        self._original_cwd = os.getcwd()
        self._tmpdir = tempfile.TemporaryDirectory()
        os.chdir(self._tmpdir.name)

    def tearDown(self):
        os.chdir(self._original_cwd)
        self._tmpdir.cleanup()

    def _write_allowlist(self, content: str) -> None:
        pathlib.Path("allowlist.json").write_text(content, encoding="utf-8")

    def _write_allowlist_obj(self, obj: object) -> None:
        self._write_allowlist(json.dumps(obj))

    # ------------------------------------------------------------------
    # Tests that PASS now — existing behaviour is already correct
    # ------------------------------------------------------------------

    def test_missing_allowlist_returns_default(self):
        """No allowlist.json → load_allowlist returns empty {paths, patterns}."""
        result = load_allowlist()
        self.assertEqual(result, {"paths": [], "patterns": []})

    def test_invalid_json_raises_scanner_error(self):
        """Unparseable JSON in allowlist.json raises ScannerError."""
        self._write_allowlist("this is not json {{{[")
        with self.assertRaises(ScannerError) as ctx:
            load_allowlist()
        self.assertIn("Failed to parse allowlist.json", str(ctx.exception))

    def test_valid_patterns_load_without_error(self):
        """Well-formed allowlist with valid regex patterns is accepted."""
        self._write_allowlist_obj({
            "paths": ["tests/fixtures/"],
            "patterns": [
                r"^tests/.*",
                r"\.env\.example$",
                r"[a-f0-9]{32}",
            ],
        })
        result = load_allowlist()
        self.assertEqual(result["paths"], ["tests/fixtures/"])
        self.assertEqual(len(result["patterns"]), 3)
        # All patterns must be valid regexes
        for p in result["patterns"]:
            re.compile(p)  # should not raise

    @patch("scanner._run_git_command")
    @patch("scanner.load_allowlist")
    def test_pattern_allowlist_excludes_matching_lines(
        self, mock_load, mock_git
    ):
        """A valid allowlist pattern excludes lines that match it."""
        mock_load.return_value = {
            "paths": [],
            "patterns": [r"^\s*#\s*noqa:?\s*(secret|key)?"],
        }

        def _git_effect(args):
            if args[1] == "diff":
                return b"src/app.py\x00"
            if args[1] == "cat-file":
                return b"512"
            if args[1] == "show":
                return (
                    b'# noqa: secret\n'
                    b'API_KEY = "sk-1234567890abcdefghij1234567890"\n'
                )
            return b""
        mock_git.side_effect = _git_effect

        findings = scan_repository()

        # The secret on the second line should still be caught; the comment
        # on the first line is allowlisted.
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file_path, "src/app.py")
        self.assertEqual(findings[0].line_number, 2)

    # ------------------------------------------------------------------
    # Validation rejection tests — all passing after Phase 2
    # ------------------------------------------------------------------

    def test_allowlist_exceeds_max_size_rejected(self):
        """allowlist.json > 64 KB must raise ScannerError (not accepted)."""
        # JSON wrapper is ~35 bytes; 65536 'x' chars pushes total past 64 KiB.
        big = {
            "paths": [],
            "patterns": ["x" * 65536],
        }
        self._write_allowlist_obj(big)
        with self.assertRaises(ScannerError) as ctx:
            load_allowlist()
        self.assertIn("64", str(ctx.exception).lower())

    def test_allowlist_top_level_not_dict_rejected(self):
        """Top-level JSON array is not a valid allowlist → ScannerError."""
        self._write_allowlist_obj(["paths", "patterns"])
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_allowlist_missing_required_keys_rejected(self):
        """Object without 'paths' AND 'patterns' keys → ScannerError."""
        self._write_allowlist_obj({"wrong_key": []})
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_allowlist_paths_not_list_rejected(self):
        """'paths' that is not a list → ScannerError."""
        self._write_allowlist_obj({"paths": "not-a-list", "patterns": []})
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_allowlist_patterns_not_list_rejected(self):
        """'patterns' that is not a list → ScannerError."""
        self._write_allowlist_obj({"paths": [], "patterns": {"oops": 1}})
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_allowlist_paths_not_all_strings_rejected(self):
        """Non-string elements inside 'paths' → ScannerError."""
        self._write_allowlist_obj({"paths": ["ok", 123, None], "patterns": []})
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_allowlist_patterns_not_all_strings_rejected(self):
        """Non-string elements inside 'patterns' → ScannerError."""
        self._write_allowlist_obj({
            "paths": [],
            "patterns": ["ok", 456, {"nested": True}],
        })
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_regex_exceeds_max_length_rejected(self):
        """Pattern longer than 256 chars → ScannerError."""
        self._write_allowlist_obj({"paths": [], "patterns": ["a" * 257]})
        with self.assertRaises(ScannerError) as ctx:
            load_allowlist()
        self.assertIn("256", str(ctx.exception))

    def test_regex_at_max_length_accepted(self):
        """Pattern at exactly 256 chars is accepted (boundary)."""
        self._write_allowlist_obj({"paths": [], "patterns": ["a" * 256]})
        result = load_allowlist()
        self.assertEqual(len(result["patterns"]), 1)
        re.compile(result["patterns"][0])  # must be a valid regex

    def test_dangerous_nested_quantifier_a_plus_rejected(self):
        """ReDoS pattern (a+)+b → ScannerError (nested quantifier)."""
        self._write_allowlist_obj({"paths": [], "patterns": ["(a+)+b"]})
        with self.assertRaises(ScannerError):
            load_allowlist()

    def test_dangerous_alternation_quantifier_rejected(self):
        """ReDoS pattern (x|x+)+y → ScannerError (alternation + nested quantifier)."""
        self._write_allowlist_obj({"paths": [], "patterns": ["(x|x+)+y"]})
        with self.assertRaises(ScannerError):
            load_allowlist()


if __name__ == "__main__":
    unittest.main()
