import re
from dataclasses import dataclass
from typing import List
from findings import Severity

@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    severity: Severity
    description: str

# Pre-compiled deterministic regex rules
RULES: List[Rule] = [
    Rule(
        name="OpenAI",
        pattern=re.compile(r"(?i)sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        severity=Severity.CRITICAL,
        description="OpenAI API key detected"
    ),
    Rule(
        name="Anthropic",
        pattern=re.compile(r"sk-ant-api03-[A-Za-z0-9\-_]{20,}"),
        severity=Severity.CRITICAL,
        description="Anthropic API key detected"
    ),
    Rule(
        name="Google Gemini",
        pattern=re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
        severity=Severity.CRITICAL,
        description="Google Gemini API key detected"
    ),
    Rule(
        name="Groq",
        pattern=re.compile(r"gsk_[A-Za-z0-9]{24,}"),
        severity=Severity.CRITICAL,
        description="Groq API key detected"
    ),
    Rule(
        name="GitHub",
        pattern=re.compile(r"(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}"),
        severity=Severity.CRITICAL,
        description="GitHub token detected"
    ),
    Rule(
        name="AWS",
        pattern=re.compile(r"AKIA[0-9A-Z]{16}"),
        severity=Severity.CRITICAL,
        description="AWS Access Key ID detected"
    ),
    Rule(
        name="Stripe Live",
        pattern=re.compile(r"(sk_live|rk_live)_[0-9a-zA-Z]{24}"),
        severity=Severity.CRITICAL,
        description="Stripe Live API key detected"
    ),
    Rule(
        name="Generic Password",
        pattern=re.compile(r'(?i)(?:password|passwd|pwd|secret)\s*[:=]\s*["\'][^"\']+["\']'),
        severity=Severity.LOW,
        description="Generic password assignment detected"
    )
]

# Hard-coded Exclusions
EXCLUDED_DIRS = {
    "tests",
    "fixtures",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build"
}

EXCLUDED_EXTENSIONS = {
    ".sqlite",
    ".db",
    ".pyc"
}

EXCLUDED_FILES = {
    "package-lock.json",
    "yarn.lock"
}

# Testing keywords for severity downgrade
TESTING_KEYWORDS = {
    "test", "fake", "dummy", "example", "sample", 
    "placeholder", "changeme", "your-key-here", "xxx"
}
