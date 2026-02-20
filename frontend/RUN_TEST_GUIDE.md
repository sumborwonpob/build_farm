# Writing run_test.sh for Build Farm

## Overview

Your repository must include a `run_test.sh` script in the root directory. This script is executed by the build farm to test your code.

## Basic Requirements

1. **Location**: Must be in repository root as `run_test.sh`
2. **Executable**: Will be made executable automatically
3. **Exit Code**: Exit with `0` for success, non-zero for failure
4. **Output (REQUIRED)**: Must create `test_results.json` with structured test results
5. **SSH Access**: Repository must be accessible via SSH (SSH key must already be configured)

## Test Duration Tracking

The build farm automatically tracks:
- **Total duration**: From clone to completion
- **Test duration**: Time to execute `run_test.sh` script
- Both are displayed in Build History with individual test results

## Structured Test Results (REQUIRED)

Your script **MUST** create a `test_results.json` file in JSON array format:

```json
[
  {
    "name": "Build",
    "success": true
  },
  {
    "name": "Unit Tests",
    "success": true
  },
  {
    "name": "Integration Tests",
    "success": false
  }
]
```

### Validation Rules:
- **Must be valid JSON** - Syntax errors will fail the build
- **Must be an array** - `[...]` not `{...}`
- **Each element must have**:
  - `"name"` (string): Test name to display in UI
  - `"success"` (boolean): `true` if passed, `false` if failed
- **If JSON is invalid or missing**: Build automatically fails (exit code -4)
- **Script exit code must be 0**: Even with test_results.json, non-zero exit fails build

## Example Scripts

### Simple Example (No Dependencies)

```bash
#!/bin/bash
set -e

# Start JSON array
cat > test_results.json << 'EOF'
[
EOF

test_count=0

# Helper function
add_test() {
    local name="$1"
    local success="$2"
    
    [ $test_count -gt 0 ] && echo "," >> test_results.json
    echo "  {\"name\": \"$name\", \"success\": $success}" >> test_results.json
    test_count=$((test_count + 1))
}

# Run tests
echo "Building..."
if make build; then
    add_test "Build" true
else
    add_test "Build" false
    echo "]" >> test_results.json
    exit 1
fi

echo "Testing..."
if make test; then
    add_test "Tests" true
else
    add_test "Tests" false
    echo "]" >> test_results.json
    exit 1
fi

# Close JSON
echo "" >> test_results.json
echo "]" >> test_results.json

exit 0
```

### Python Example

```bash
#!/bin/bash
set -e

# Install dependencies
pip install -q -r requirements.txt

# Initialize results
python3 << 'PYTHON'
import json
import subprocess
import sys

results = []

# Test 1: Build/Install
try:
    subprocess.run(["python", "setup.py", "build"], check=True, capture_output=True)
    results.append({"name": "Build", "success": True})
except:
    results.append({"name": "Build", "success": False})
    with open('test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    sys.exit(1)

# Test 2: Unit Tests
try:
    subprocess.run(["pytest", "tests/"], check=True, capture_output=True)
    results.append({"name": "Unit Tests", "success": True})
except:
    results.append({"name": "Unit Tests", "success": False})

# Test 3: Linting (optional)
try:
    subprocess.run(["pylint", "src/"], check=True, capture_output=True)
    results.append({"name": "Linting", "success": True})
except:
    results.append({"name": "Linting", "success": False})

# Save results
with open('test_results.json', 'w') as f:
    json.dump(results, f, indent=2)

# Exit with failure if any critical test failed
if not results[1]["success"]:  # Unit tests
    sys.exit(1)

PYTHON
```

### Node.js Example

```bash
#!/bin/bash
set -e

npm install

# Run tests and capture results
node << 'NODEJS'
const { execSync } = require('child_process');
const fs = require('fs');

const results = [];

// Test 1: Build
try {
  execSync('npm run build', { stdio: 'pipe' });
  results.push({ name: 'Build', success: true });
} catch {
  results.push({ name: 'Build', success: false });
  fs.writeFileSync('test_results.json', JSON.stringify(results, null, 2));
  process.exit(1);
}

// Test 2: Unit Tests
try {
  execSync('npm test', { stdio: 'pipe' });
  results.push({ name: 'Tests', success: true });
} catch {
  results.push({ name: 'Tests', success: false });
}

// Save results
fs.writeFileSync('test_results.json', JSON.stringify(results, null, 2));

// Exit with error if tests failed
if (!results[results.length - 1].success) {
  process.exit(1);
}
NODEJS
```

## Tips

1. **Use `set -e`**: Script exits immediately on any error
2. **Capture output**: Redirect output to control what appears in logs
3. **Timeout**: Scripts timeout after 1 hour
4. **Cleanup**: Build farm automatically cleans up workspace after execution
5. **Optional tests**: Don't exit on non-critical test failures, just record them
6. **Dependencies**: Install all dependencies in the script

## Testing Locally

Test your script before pushing:

```bash
cd your-repo/
bash run_test.sh
cat test_results.json  # Check output
echo $?  # Check exit code (should be 0)
```

## What Gets Tracked

The build farm UI displays:
- ✅/❌ Overall build status
- 📊 Individual test results from `test_results.json`
- ⏱️ Total duration (clone + test)
- ⏱️ Test execution duration
- 📝 Complete logs (stdout/stderr)
- 🔖 Git commit hash and message
- 🔢 Exit code
