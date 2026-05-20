import sys
import pathlib
import unittest
from unittest.mock import patch

# Add root to sys.path for testing
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from scanner import is_excluded, scan_repository, ScannerError
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

if __name__ == "__main__":
    unittest.main()
