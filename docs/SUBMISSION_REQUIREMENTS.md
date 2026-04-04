# Submission Requirements — Round 1

## Deadline

**April 8, 2026 at 11:59 PM**

---

## Deliverables Checklist

### Required Files

- [ ] `models.py` — Typed Pydantic models (Action, Observation, State)
- [ ] `server/environment.py` — Core environment logic
- [ ] `server/app.py` — FastAPI application with `main()` entry point
- [ ] `server/__init__.py` — Package marker
- [ ] `client.py` — EnvClient subclass
- [ ] `openenv.yaml` — Environment manifest metadata
- [ ] `pyproject.toml` — Project configuration with dependencies
- [ ] `requirements.txt` — Docker dependencies
- [ ] `Dockerfile` — Containerized execution
- [ ] `inference.py` — Baseline inference script (**must be in root directory**)
- [ ] `README.md` — Documentation
- [ ] `uv.lock` — Lock file (required by `openenv validate`)

### README Must Include

- Environment description and motivation
- Action and observation space definitions
- Task descriptions with expected difficulty
- Setup and usage instructions
- Baseline scores

---

## Functional Requirements

### 1. Real-world task simulation
The environment must simulate a task humans actually do. **Not games, not toys.** Examples: email triage, code review, data cleaning, scheduling, customer support, content moderation.

### 2. OpenEnv spec compliance
- Typed `Observation`, `Action`, and `Reward` Pydantic models
- `step(action)` → returns observation, reward, done, info
- `reset()` → returns initial observation
- `state()` → returns current state
- `openenv.yaml` with metadata
- Must pass `openenv validate`

### 3. Minimum 3 tasks with agent graders
- Each task defines a concrete objective with a programmatic grader
- Scores in range **0.0–1.0**
- Tasks should range: **easy → medium → hard**
- Graders must have clear, deterministic success/failure criteria

### 4. Meaningful reward function
- Provides signal over the full trajectory (not just binary end-of-episode)
- Rewards partial progress toward task completion
- Penalizes clearly undesirable behavior (e.g. infinite loops, destructive actions)

### 5. Baseline inference script
- Uses the **OpenAI API client** for all LLM calls
- Reads credentials from environment variables
- Produces reproducible baseline scores on all 3 tasks

---

## Infrastructure Constraints

| Constraint | Requirement |
|------------|-------------|
| **Runtime** | inference.py must complete in **< 20 minutes** |
| **Hardware** | Must run on **2 vCPU, 8 GB RAM** |
| **LLM Client** | Must use **OpenAI Client** for all LLM calls |
| **Deployment** | Must deploy to **Hugging Face Spaces** |
| **Container** | Must include working **Dockerfile** (`docker build` + `docker run`) |

---

## Mandatory Environment Variables

Your environment configuration must use these variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `API_BASE_URL` | The API endpoint for the LLM | `https://router.huggingface.co/v1` |
| `MODEL_NAME` | The model identifier to use for inference | (must reflect your active model) |
| `HF_TOKEN` | Your Hugging Face / API key | (required, no default) |
| `LOCAL_IMAGE_NAME` | Docker image name if using `from_docker_image()` | (optional) |

Defaults are set only for `API_BASE_URL` and `MODEL_NAME`.

---

## Inference Script Logging Format (MANDATORY — EXACT FORMAT)

The inference script **must emit exactly three line types to stdout**, in this order. Any deviation in field names, ordering, or formatting will result in incorrect evaluation scoring.

```
[START] task=<task_name> env=<benchmark> model=<model_name>
[STEP] step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
[END] success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
```

### Rules

- One `[START]` line at episode begin
- One `[STEP]` line per step, immediately after `env.step()` returns
- One `[END]` line after `env.close()`, **always emitted** (even on exception)
- `reward` and `rewards` are formatted to **2 decimal places**
- `done` and `success` are **lowercase booleans**: `true` or `false`
- `error` is the raw last_action_error string, or `null` if none
- All fields on a single line with no newlines within a line
- Each task should return score in `[0, 1]`

### Example Output

```
[START] task=easy env=sre_incident_commander model=meta-llama/Llama-3.3-70B-Instruct
[STEP] step=1 action=scale_service(worker-node,5) reward=0.20 done=false error=null
[STEP] step=2 action=query_logs(worker-node) reward=0.00 done=false error=null
[STEP] step=3 action=query_logs(worker-node) reward=0.20 done=true error=null
[END] success=true steps=3 score=1.00 rewards=0.20,0.00,0.20
```

---

## Pre-Submission Validation

Run the validation script before submitting:

```bash
# Local validation
openenv validate

# Full validation against deployed Space
curl -fsSL <validation_script_url> | bash -s -- <your_hf_space_url> [repo_dir]
```

The validation script checks:
1. HF Space is live and responds to `/reset` (HTTP 200)
2. Docker image builds successfully
3. `openenv validate` passes

---

## Submission

Submit through the hackathon dashboard:
https://www.scaler.com/school-of-technology/meta-pytorch-hackathon/dashboard
