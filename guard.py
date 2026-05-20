import sys
import click
from git_hooks import install_hook as do_install_hook, HookError
from scanner import scan_repository, ScannerError
from findings import Severity

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """repo-guard CLI"""
    if ctx.invoked_subcommand is None:
        # Default to scan if no subcommand is provided
        # This allows the raw hook execution `python guard.py` to work correctly.
        ctx.invoke(scan)

@cli.command()
def install_hook():
    """Install the git pre-commit hook safely."""
    try:
        do_install_hook()
    except HookError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(2)

@cli.command()
def scan():
    """Scan staged files for secrets."""
    try:
        findings = scan_repository()
    except ScannerError as e:
        sys.stderr.write(f"Scanner Error: {e}\n")
        sys.exit(2)
        
    has_blocking_finding = False
    
    for finding in findings:
        # Print formatted findings to stdout
        sys.stdout.write(finding.format_terminal() + "\n\n")
        
        if finding.severity in (Severity.HIGH, Severity.CRITICAL):
            has_blocking_finding = True
            
    if has_blocking_finding:
        sys.stderr.write("[CRITICAL] Blocking findings detected. Commit blocked.\n")
        sys.exit(1)
        
    sys.exit(0)

if __name__ == "__main__":
    cli()
