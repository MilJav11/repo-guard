#!/bin/bash
set -e

# Setup colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting repo-guard E2E tests...${NC}"

# Get the absolute path to the repo-guard source directory
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Create a temporary directory
TEMP_DIR=$(mktemp -d)
echo "Setting up temporary git repository in $TEMP_DIR"

cleanup() {
    echo -e "\nCleaning up temporary directory..."
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

cd "$TEMP_DIR"

# Initialize git repository
git init -b master
git config user.name "E2E QA Bot"
git config user.email "qa@repo-guard.local"

# Copy the app files into the temp directory
cp -r "$SOURCE_DIR"/*.py .
# If there is a requirements file, copy it just in case
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    cp "$SOURCE_DIR/requirements.txt" .
fi

# Find python executable
PYTHON_CMD="python"
if ! command -v python &> /dev/null; then
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v py &> /dev/null; then
        PYTHON_CMD="py"
    elif command -v python.exe &> /dev/null; then
        PYTHON_CMD="python.exe"
    fi
fi

# The git hook hardcodes 'exec python'. If the environment only has 'python3', git commit will fail.
# Create a wrapper script in the temp dir and prepend to PATH to satisfy the hook.
mkdir -p "$TEMP_DIR/bin"
cat <<EOF > "$TEMP_DIR/bin/python"
#!/bin/sh
exec $PYTHON_CMD "\$@"
EOF
chmod +x "$TEMP_DIR/bin/python"
export PATH="$TEMP_DIR/bin:$PATH"

# Install the hook
echo "Installing hook using $PYTHON_CMD..."
$PYTHON_CMD guard.py install-hook

# Create an initial commit
echo "Initial commit..."
git add .
git commit -m "Initial commit" --no-verify

# Helper function to check if a commit succeeds or fails
expect_commit_fail() {
    local msg="$1"
    set +e
    output=$(git commit -m "$msg" 2>&1)
    exit_code=$?
    set -e
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${RED}FAIL: Commit '$msg' should have been blocked (exit code 0)${NC}"
        echo "Output:"
        echo "$output"
        exit 1
    else
        echo -e "${GREEN}PASS: Commit '$msg' successfully blocked (exit code $exit_code)${NC}"
        return 0
    fi
}

expect_commit_pass() {
    local msg="$1"
    set +e
    output=$(git commit -m "$msg" 2>&1)
    exit_code=$?
    set -e
    
    if [ $exit_code -ne 0 ]; then
        echo -e "${RED}FAIL: Commit '$msg' should have passed (exit code $exit_code)${NC}"
        echo "Output:"
        echo "$output"
        exit 1
    else
        echo -e "${GREEN}PASS: Commit '$msg' successfully passed${NC}"
        # Echo the output so it can be captured by the caller
        echo "$output"
        return 0
    fi
}

echo -e "\n${BLUE}--- Scenario A: The Direct Block ---${NC}"
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' > secret.py
git add secret.py
expect_commit_fail "Scenario A commit"
git rm -f secret.py

echo -e "\n${BLUE}--- Scenario B: The Index vs. Working Tree Separation (CRITICAL) ---${NC}"
echo "print('This is a safe file without secrets')" > safe.py
git add safe.py
# Modify the file on disk after staging to include a secret
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' >> safe.py
expect_commit_pass "Scenario B commit"
# Clean up the working tree
git rm -f safe.py
git commit -m "Cleanup safe.py" --no-verify

echo -e "\n${BLUE}--- Scenario C: Filenames with Spaces ---${NC}"
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' > "my weird config.py"
git add "my weird config.py"
expect_commit_fail "Scenario C commit"
git rm -f "my weird config.py"

echo -e "\n${BLUE}--- Scenario D: Allowlist & Testing Keyword Bypass ---${NC}"
echo '{ "paths": ["tests/fixtures/"] }' > allowlist.json
mkdir -p tests/fixtures/
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' > tests/fixtures/secret.py
echo 'API_KEY="sk-test-1234567890abcdefghij123456"' > test_mock.py
git add allowlist.json tests/fixtures/secret.py test_mock.py
expect_commit_pass "Scenario D commit"

echo -e "\n${BLUE}--- Scenario E: Binary & .env DX Warning ---${NC}"
touch .env
printf "dummy\x00data" > dummy.bin
git add .env dummy.bin

output=$(expect_commit_pass "Scenario E commit")
if echo "$output" | grep -qi "WARNING: .env file staged for commit"; then
    echo -e "${GREEN}PASS: Warning was printed to stderr correctly for .env file${NC}"
else
    echo -e "${RED}FAIL: Warning was NOT printed for .env file${NC}"
    echo "Output was:"
    echo "$output"
    exit 1
fi

echo -e "\n${BLUE}--- Scenario 1: EXISTING PRE-COMMIT HOOK SAFETY ---${NC}"
rm -f .git/hooks/pre-commit .git/hooks/pre-commit.bak.*
echo "#!/bin/sh" > .git/hooks/pre-commit
echo "echo 'legacy hook'" >> .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

$PYTHON_CMD guard.py install-hook
if ! ls .git/hooks/pre-commit.bak.* 1> /dev/null 2>&1; then
    echo -e "${RED}FAIL: Backup file was not created${NC}"
    exit 1
fi
if ! grep -q "# repo-guard hook start" .git/hooks/pre-commit; then
    echo -e "${RED}FAIL: repo-guard markers missing in hook${NC}"
    exit 1
fi
echo -e "${GREEN}PASS: Existing hook safely backed up and modified${NC}"

echo -e "\n${BLUE}--- Scenario 2: HOOK IDEMPOTENCY ---${NC}"
$PYTHON_CMD guard.py install-hook
COUNT=$(grep -c "# repo-guard hook start" .git/hooks/pre-commit || true)
if [ "$COUNT" -ne 1 ]; then
    echo -e "${RED}FAIL: Idempotency failed, start marker count is $COUNT${NC}"
    exit 1
fi
echo -e "${GREEN}PASS: Hook installation is idempotent${NC}"

echo -e "\n${BLUE}--- Scenario 3: OVERSIZED FILE SKIP ---${NC}"
dd if=/dev/zero of=huge.bin bs=1M count=2 2>/dev/null
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' >> huge.bin
git add huge.bin
expect_commit_pass "Scenario 3 commit"
git rm -f huge.bin

echo -e "\n${BLUE}--- Scenario 4: CORRUPTED allowlist.json ---${NC}"
echo '{ "paths": [' > allowlist.json
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' > secret2.py
git add allowlist.json secret2.py

set +e
$PYTHON_CMD guard.py scan > scan_out.txt 2>&1
exit_code=$?
set -e

if [ $exit_code -ne 2 ]; then
    echo -e "${RED}FAIL: guard.py scan should exit with 2, got $exit_code${NC}"
    cat scan_out.txt
    exit 1
fi
if ! grep -qi "Failed to parse allowlist.json" scan_out.txt; then
    echo -e "${RED}FAIL: Did not see explicit error message${NC}"
    cat scan_out.txt
    exit 1
fi
echo -e "${GREEN}PASS: Corrupted allowlist handled correctly${NC}"
git reset HEAD allowlist.json secret2.py > /dev/null
rm allowlist.json secret2.py

echo -e "\n${BLUE}--- Scenario 5: INTERNAL FAILURE HANDLING ---${NC}"
PYTHON_ABS=$($PYTHON_CMD -c "import sys, os; print(sys.executable.replace(os.sep, '/'))")
mkdir -p /tmp/empty_path_dir
set +e
PATH="/tmp/empty_path_dir" "$PYTHON_ABS" guard.py scan > scan_out.txt 2>&1
exit_code=$?
set -e

if [ $exit_code -ne 2 ]; then
    echo -e "${RED}FAIL: Expected exit code 2 when git is missing, got $exit_code${NC}"
    cat scan_out.txt
    exit 1
fi
if ! grep -qi "Git is not installed or not available in PATH" scan_out.txt; then
    echo -e "${RED}FAIL: Did not see explicit git missing error message${NC}"
    cat scan_out.txt
    exit 1
fi
if grep -qi "Traceback" scan_out.txt; then
    echo -e "${RED}FAIL: Saw raw traceback in output${NC}"
    cat scan_out.txt
    exit 1
fi
echo -e "${GREEN}PASS: Internal failure handled gracefully${NC}"

echo -e "\n${BLUE}--- Scenario 6: PARTIALLY STAGED FILE ---${NC}"
echo "line 1 safe" > partial.py
echo "line 2 safe" >> partial.py
git add partial.py
git commit -m "Initial partial" > /dev/null
echo "line 1 modified safe" > partial.py
echo "line 2 safe" >> partial.py
git add partial.py
echo 'API_KEY="sk-proj-1234567890abcdefghij1234567890abcdefghij"' >> partial.py
expect_commit_pass "Scenario 6 commit"
git rm -f partial.py

echo -e "\n${GREEN}✅ ALL E2E TESTS PASSED${NC}"
