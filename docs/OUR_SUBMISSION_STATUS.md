# Our Submission Status — SRE Incident Commander

## Environment: `sre_incident_commander`

An AI agent acts as Incident Commander diagnosing and resolving production infrastructure incidents using mock services, metrics, alerts, and logs.

**GitHub**: https://github.com/MUDITGUPTA08/Triage

---

## Pre-Submission Checklist (All must pass or DISQUALIFIED)

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | HF Space deploys, returns 200, responds to `reset()` | **TODO** | Need to deploy to HF Spaces |
| 2 | `openenv validate` passes | **PASS** | `[OK] meta: Ready for multi-mode deployment` |
| 3 | Dockerfile builds | **TODO** | Need to test `docker build` |
| 4 | Baseline `inference.py` runs without error, produces scores | **TODO** | Need HF_TOKEN + running server |
| 5 | 3+ tasks with graders, scores 0.0–1.0 | **PASS** | easy, medium, hard — all verified |
| 6 | `inference.py` emits correct `[START]/[STEP]/[END]` format | **PASS** | Updated to match mandatory spec |
| 7 | Uses OpenAI Client for LLM calls | **PASS** | `from openai import OpenAI` |
| 8 | Env vars: `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN` | **PASS** | All defined with proper defaults |

---

## Scoring Criteria Self-Assessment

### Real-world utility (30%) — Target: 26–30

- SRE incident response is a genuine task performed daily at every tech company
- Not a game or toy — actual infrastructure diagnosis workflow
- Would be valuable for training/evaluating AI agents for DevOps/SRE roles
- Novel domain not yet seen in OpenEnv ecosystem

### Task & grader quality (25%) — Target: 20–25

- 3 tasks: easy (Traffic Spike), medium (Poison Pill), hard (Cascading Lock)
- All graders produce scores in 0.0–1.0 range
- Graders are deterministic and reproducible
- Hard task (Cascading Lock) requires 5-step diagnostic chain — genuinely challenging
- Difficulty progression is natural and well-motivated

### Environment design (20%) — Target: 16–20

- `reset()` produces clean state with deep-copied task config
- Action types: 5 Literal types with clear Pydantic validation
- Observation includes alerts, metrics, logs, services, feedback, hints
- Shaped reward function with partial progress signals (not sparse)
- Penalties for bad actions (-0.5 for scaling a broken service)
- Episode boundaries: auto-resolve on success, max-step cutoff
- Cost model: $0.50/step + 1 min downtime

### Code quality & spec compliance (15%) — Target: 13–15

- `openenv validate` passes
- Clean project structure matching OpenEnv conventions
- Typed Pydantic models (SREAction, SREObservation, SREState)
- Dual-import pattern for Docker compatibility
- `pyproject.toml` with proper `[project.scripts]` entry
- README with all required sections

### Creativity & novelty (10%) — Target: 8–10

- SRE incident response is a novel domain for OpenEnv
- Interesting mechanics: diagnostic log chains, cascading failures, state machines
- Clever reward design: trap actions (scaling a buggy service = -0.5)
- Progressive hints for stuck agents

---

## Optimal Scores (Verified)

| Task | Optimal Steps | Score | Sequence |
|------|---------------|-------|----------|
| Easy | 3 | 1.000 | scale(5) → wait → auto-resolve |
| Medium | 2 | 1.000 | query_logs → rollback(v2.0.9) |
| Hard | 5 | 1.000 | query×3 → kill(4287) → scale(5) |

---

## Remaining TODOs

1. **Deploy to Hugging Face Spaces** (tagged with `openenv`)
2. **Test Docker build** locally (`docker build -t sre-incident-env .`)
3. **Run full validation script** against deployed Space
4. **Run `inference.py`** with actual LLM to verify baseline scores
5. **Submit** on dashboard before April 8, 11:59 PM
