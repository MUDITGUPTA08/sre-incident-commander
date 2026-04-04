# Pre-Submission Validation Script

## What It Checks

The validation script (`validate-submission.sh`) performs 3 sequential checks. All must pass.

### Step 1/3: Ping HF Space

- Sends `POST /reset` with `{}` body to your HF Space URL
- Must return HTTP 200
- Timeout: 30 seconds

### Step 2/3: Docker Build

- Looks for `Dockerfile` in repo root or `server/` directory
- Runs `docker build` with 600-second timeout
- Must succeed (exit code 0)

### Step 3/3: OpenEnv Validate

- Runs `openenv validate` in the repo directory
- Checks all structural requirements (see OPENENV_FRAMEWORK.md)
- Must pass with no issues

---

## How to Run

### Against a deployed HF Space

```bash
# Download and run
curl -fsSL <script_url> | bash -s -- https://your-space.hf.space

# Or with explicit repo directory
./validate-submission.sh https://your-space.hf.space ./my-repo
```

### Local checks only

```bash
# Just openenv validate
cd /path/to/repo
openenv validate

# Docker build test
docker build -t sre-incident-env .
docker run -p 7860:7860 sre-incident-env
# Then in another terminal:
curl -s -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{}'
```

---

## Prerequisites

- **Docker**: https://docs.docker.com/get-docker/
- **openenv-core**: `pip install openenv-core`
- **curl**: Usually pre-installed

---

## Our Current Status

```
Step 1 (HF Space ping):     TODO — need to deploy
Step 2 (Docker build):      TODO — need to test
Step 3 (openenv validate):  PASS
```

---

## Validation Script Details

The script:
- Uses colored output (green/red/yellow) in terminals
- Stops at first failure (no point continuing)
- Shows hints for common issues
- Has portable timeout handling (works on macOS/Linux)
- Creates temp files for curl output, auto-cleans on exit
