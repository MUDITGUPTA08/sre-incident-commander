# Judging Criteria & Scoring Breakdown

## Evaluation Weights

| Parameter | Weight | Description |
|-----------|--------|-------------|
| **Real-world utility** | **30%** | Does the environment model a genuine task? Would someone actually use this to train or evaluate agents? |
| **Task & grader quality** | **25%** | Are tasks well-defined with clear objectives? Do graders accurately and fairly measure success? Meaningful difficulty progression? |
| **Environment design** | **20%** | Clean state management, sensible action/observation spaces, good reward shaping, proper episode boundaries. |
| **Code quality & spec compliance** | **15%** | Follows OpenEnv spec, clean project structure, typed models, documented, tested, Dockerfile works. |
| **Creativity & novelty** | **10%** | Novel problem domain, interesting mechanics, clever reward design, original approach. |

---

## Detailed Scoring Rubric

### Real-world utility (30%)

| Score | Description |
|-------|-------------|
| 0–5 | Toy/artificial problem with no practical application |
| 6–15 | Valid domain but shallow modeling of the real task |
| 16–25 | Good domain modeling, would be useful for agent evaluation |
| 26–30 | Excellent — fills a real gap, immediate value for the RL/agent community |

### Task & grader quality (25%)

- 3+ tasks with difficulty range?
- Graders produce scores between 0.0–1.0?
- Graders deterministic and reproducible?
- Hard task genuinely challenges frontier models?

### Environment design (20%)

- `reset()` produces clean state?
- Action/observation types well-designed and documented?
- Reward function provides useful varying signal (not just sparse)?
- Episode boundaries sensible?

### Code quality & spec compliance (15%)

- `openenv validate` passes?
- `docker build && docker run` works?
- HF Space deploys and responds?
- Baseline script runs and reproduces scores?

### Creativity & novelty (10%)

- Domain we haven't seen in OpenEnv before?
- Reward design has interesting properties?
- Clever mechanics that make the environment engaging?

---

## Three-Phase Evaluation Process

### Phase 1: Automated Validation (Pass/Fail Gate)

All must pass or you're **disqualified**:

1. **HF Space deploys** — Automated ping to Space URL, must return 200 and respond to `reset()`
2. **OpenEnv spec compliance** — Validate `openenv.yaml`, typed models, `step()/reset()/state()` endpoints
3. **Dockerfile builds** — Automated `docker build` on submitted repo
4. **Baseline reproduces** — Run submitted `inference.py`, must complete without error and produce scores
5. **3+ tasks with graders** — Enumerate tasks, run each grader, verify scores/reward in 0.0–1.0 range

### Phase 2: Agentic Evaluation (Scored)

- Baseline agent re-run
- Standard Open LLM agent (e.g. Nemotron 3 Super) run against all environments
- Score variance check

### Phase 3: Human Review

- Top submissions reviewed by **Meta and Hugging Face engineers**
- Evaluated for real-world utility, creativity, and exploit checks

---

## Disqualification Criteria

- Environment does not deploy or respond
- Plagiarized or trivially modified existing environments
- Graders that always return the same score
- No baseline inference script
