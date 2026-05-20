import sys
import pathlib
import unittest

# Add root to sys.path for testing
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rules import RULES, Rule
from findings import Severity

class TestRules(unittest.TestCase):
    def get_rule(self, name: str) -> Rule:
        for r in RULES:
            if r.name == name:
                return r
        raise ValueError(f"Rule {name} not found")

    def test_openai_rule(self):
        rule = self.get_rule("OpenAI")
        # Positive matches
        self.assertIsNotNone(rule.pattern.search("sk-1234567890abcdefghij1234567890"))
        self.assertIsNotNone(rule.pattern.search("sk-proj-1234567890abcdefghij1234567890"))
        
        # Negative matches
        self.assertIsNone(rule.pattern.search("sk-123")) # too short
        self.assertIsNone(rule.pattern.search("some-other-key-format-1234567890abcdef"))

    def test_github_rule(self):
        rule = self.get_rule("GitHub")
        self.assertIsNotNone(rule.pattern.search("ghp_1234567890abcdefghij1234567890abcdef"))
        self.assertIsNone(rule.pattern.search("ghp_123"))

    def test_generic_password_rule(self):
        rule = self.get_rule("Generic Password")
        self.assertIsNotNone(rule.pattern.search('password = "mysecretpassword"'))
        self.assertIsNotNone(rule.pattern.search("pwd:'super_secret_123'"))
        
        # Should not match without quotes in the assignment for this specific regex
        self.assertIsNone(rule.pattern.search("password = function_call()"))
        self.assertIsNone(rule.pattern.search("pwd = 12345"))

    def test_windows_line_endings(self):
        rule = self.get_rule("OpenAI")
        match = rule.pattern.search("API_KEY='sk-1234567890abcdefghij1234567890'\r\n")
        self.assertIsNotNone(match)
        
        rule2 = self.get_rule("Generic Password")
        match2 = rule2.pattern.search('password = "mysecretpassword"\r\n')
        self.assertIsNotNone(match2)

if __name__ == "__main__":
    unittest.main()
