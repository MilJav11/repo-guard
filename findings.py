from enum import IntEnum
from dataclasses import dataclass

class Severity(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

@dataclass
class Finding:
    rule_name: str
    severity: Severity
    description: str
    file_path: str
    line_number: int

    def format_terminal(self) -> str:
        """
        Formats the finding exactly as required for the terminal.
        Example:
        [CRITICAL] OpenAI API key detected
        File: config.py
        Line: 18
        """
        severity_name = self.severity.name
        return (
            f"[{severity_name}] {self.description}\n"
            f"File: {self.file_path}\n"
            f"Line: {self.line_number}"
        )
