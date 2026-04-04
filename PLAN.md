# Plan: SRE Incident Commander — OpenEnv Environment

## Context

Building a competition-grade OpenEnv environment for the **Meta PyTorch OpenEnv Hackathon**. The environment simulates **SRE incident response** — an AI agent acts as Incident Commander diagnosing and resolving production infrastructure incidents using mock services, metrics, alerts, and logs.

**Why SRE Incident Commander?**
- Genuine real-world task that SREs perform daily at every tech company
- Balances diagnostic reasoning (log analysis) with sequential decision-making (action ordering)
- Natural difficulty progression: simple scaling → diagnosis + rollback → multi-step cascading failure
- All infrastructure mocked via Python dicts/state machines — zero external dependencies, runs on 2 vCPU / 8GB RAM
- Novel domain not yet seen in OpenEnv ecosystem

---

## OpenEnv Framework (Exact Base Classes)

```python
# Action: Pydantic BaseModel, extra="forbid"
class Action(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)

# Observation: Pydantic BaseModel, extra="forbid"
class Observation(BaseModel):
    done: bool = Field(default=False)
    reward: bool | int | float | None = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# State: Pydantic BaseModel, extra="allow"
class State(BaseModel):
    episode_id: Optional[str] = Field(default=None)
    step_count: int = Field(default=0, ge=0)

# Environment: Abstract base, Generic[ActT, ObsT, StateT]
class Environment(ABC, Generic[ActT, ObsT, StateT]):
    SUPPORTS_CONCURRENT_SESSIONS: bool = False
    def reset(self, seed=None, episode_id=None, **kwargs) -> ObsT: ...
    def step(self, action: ActT, timeout_s=None, **kwargs) -> ObsT: ...
    @property
    def state(self) -> StateT: ...

# Factory: env must be a callable (class or factory function)
create_fastapi_app(env, action_cls, observation_cls, max_concurrent_envs=None) -> FastAPI
```

**Dual-import pattern** (critical for Docker):
```python
try:
    from ..models import SREAction
except ImportError:
    from models import SREAction
```

---

## File Structure

```
C:\Users\mudit\Videos\meta\
├── models.py                  # Pydantic: SREAction, SREObservation, SREState
├── client.py                  # EnvClient[SREAction, SREObservation, SREState]
├── openenv.yaml               # Environment manifest
├── requirements.txt           # Docker dependencies
├── Dockerfile                 # HF Spaces (port 7860, non-root user)
├── README.md                  # Documentation
├── inference.py               # Baseline LLM agent with [START]/[STEP]/[END] logging
└── server/
    ├── __init__.py            # Empty package marker
    ├── app.py                 # FastAPI + create_fastapi_app()
    └── environment.py         # Core: mock infra, state machines, tasks, graders
```

---

## FILE 1: `models.py`

```python
from typing import Any, Dict, List, Literal, Optional
from openenv.core.env_server import Action, Observation, State

class SREAction(Action):
    action_type: Literal[
        "scale_service", "rollback_deployment",
        "query_logs", "kill_query", "resolve_incident"
    ]
    service_name: str = ""
    replicas: int = 0
    version: str = ""
    query_id: str = ""
    reasoning: str = ""

class SREObservation(Observation):
    # Inherited: done, reward, metadata
    active_alerts: List[Dict[str, Any]] = []
    system_metrics: Dict[str, Any] = {}
    queried_logs: str = ""
    cloud_cost_usd: float = 0.0
    uptime_percentage: float = 100.0
    task_id: str = ""
    difficulty: str = ""
    feedback: str = ""
    hint: str = ""
    current_deployment_version: str = ""
    services: Dict[str, Any] = {}
    attempt_number: int = 0
    max_attempts: int = 10

class SREState(State):
    # Inherited: episode_id, step_count
    task_id: str = ""
    difficulty: str = ""
    current_score: float = 0.0
    total_downtime_minutes: float = 0.0
    total_cost_usd: float = 0.0
    actions_taken: List[str] = []
    completed: bool = False
```

---

## FILE 2: `server/environment.py` (Core Logic — ~500 lines)

### Mock Data Constants

**Task 1 "The Traffic Spike":**
- 2 alerts: SQS queue backlog critical (500 messages), worker-node high CPU (92%)
- Services: api-gateway (healthy), worker-node (degraded, 2 replicas, 92% CPU), order-processing-queue (backlogged, 500 msgs), database (healthy)
- Metrics: cpu=92%, mem=68%, queue=500, error_rate=2.1%, latency=450ms, connections=45
- Logs: worker-node shows OOMKills and "scale to 5+ replicas"; queue shows +200/min growth rate

**Task 2 "The Poison Pill":**
- 2 alerts: API error rate spike (15%), deployment completed (v2.1.0)
- Services: api-gateway (degraded, v2.1.0, 15% errors), worker-node (healthy), database (healthy), cache-layer (healthy)
- Metrics: cpu=55%, mem=52%, queue=20, error_rate=15%, latency=1200ms
- Logs: api-gateway shows NullPointerException from v2.1.0 PaymentHandler, "rollback candidate: v2.0.9"

**Task 3 "The Cascading Lock":**
- 3 alerts: API gateway timeout (504s, 40% failing), worker unresponsive (3/4 CrashLoopBackOff), DB connection pool exhausted (195/200)
- Services: api-gateway (critical, 40% errors), worker-node (critical, 98% CPU, 1/4 healthy), database (degraded, 195 connections, locked queries PID 4287 + 4290), cache-layer (degraded, 12% hit rate)
- Metrics: cpu=98%, mem=85%, queue=800, error_rate=40%, latency=8500ms, connections=195
- Logs: diagnostic chain — api-gateway says "check worker-node" → worker-node says "DB timeout, check database" → database says "PID 4287 LOCKED, kill it"

### Internal `_TaskState` Class

Mutable internal state tracker (not Pydantic — plain class):
- Copies of alerts, services, metrics per episode
- Task-specific flags: `queue_length`, `worker_replicas` (task 1), `has_queried_logs`, `has_rolled_back`, `scaled_broken_service` (task 2), `queried_api_gateway_logs`, `queried_worker_logs`, `queried_db_logs`, `identified_pid`, `killed_query`, `stabilized` (task 3)

### State Machine: Task 1 — "The Traffic Spike"

```
Queue dynamics per step:
  growth = +200 messages/step
  drain  = replicas × 100 messages/step
  Initial: queue=500, replicas=2, drain=200, net=0 (queue stays at 500)

Optimal play:
  Step 1: scale_service(worker-node, 5) → +0.2 reward. queue: 500+200-500=200
  Step 2: queue: 200+200-500=0 → auto-resolved → +0.2 reward
  Total: 0.4 → normalized to 1.0

Penalties:
  - Wrong action: -0.1
  - Queue > 800 (80% of 1000 cap): -0.1 per step
  - Queue overflow (≥1000): -0.1 extra, messages "dropped", alert fires
  - Scaling down during incident: -0.1
  - resolve_incident with queue ≥ 50: -0.2

Hints after step 3 if queue still ≥ 500
```

### State Machine: Task 2 — "The Poison Pill"

```
Error rate fixed at 15% until rollback. Each step degrades uptime -0.3.

Optimal play:
  Step 1: query_logs(api-gateway) → +0.4. Logs show v2.1.0 NullPointerException.
  Step 2: rollback_deployment(api-gateway, v2.0.9) → +0.6. Error rate → 0.5%. Resolved.
  Total: 1.0

CRITICAL: scale_service(api-gateway) → -0.5 penalty
Wrong rollback version: -0.1
Wrong service: -0.1
Re-querying logs: 0.0
Premature resolve_incident: -0.2

Hints: Step 2 if no logs queried, Step 4 if logs queried but no rollback
```

### State Machine: Task 3 — "The Cascading Lock"

```
Degradation: error_rate +5%/step, latency +2000ms/step, connections +2/step until lock killed.
At 200 connections → full block alert.

Optimal play (5 steps):
  Step 1: query_logs(api-gateway)  → +0.1. "504 timeout, check worker-node"
  Step 2: query_logs(worker-node)  → +0.1. "DB timeout, check database logs"
  Step 3: query_logs(database)     → +0.1. "PID 4287 LOCKED, kill it"
  Step 4: kill_query(4287)         → +0.4. Lock freed, connections drop to 60.
  Step 5: scale_service(worker-node, ≥4) → +0.3. Backlog cleared. Resolved.
  Total: 1.0

Penalties:
  - scale before kill: -0.1 ("new workers will also get stuck")
  - rollback (not needed): -0.1
  - kill wrong PID (4290): -0.05
  - resolve before stable: -0.1 to -0.2

After kill_query succeeds: queue_length set to 600, worker status "recovering", alert says "scale to drain backlog"
After scale: queue→0, error_rate→0.5%, latency→80ms, all alerts cleared

Hints: Step 2 (check worker-node), Step 4 (check database), Step 6 (kill PID), Step 8 (scale workers)
```

### Score Normalization

```python
max_rewards = {"easy": 0.4, "medium": 1.0, "hard": 1.0}
score = clamp(cumulative_reward / max_reward, 0.0, 1.0)
```

### Cost Model

Each step adds $0.50 cloud cost + 1 minute downtime while incident is active.

---

## FILE 3: `server/app.py`

```python
from openenv.core.env_server import create_fastapi_app
# dual-import pattern for models
from server.environment import SREIncidentEnvironment, TASK_CONFIGS

app = create_fastapi_app(
    env=SREIncidentEnvironment,
    action_cls=SREAction,
    observation_cls=SREObservation,
    max_concurrent_envs=100,
)

@app.get("/")         # Service info
@app.get("/tasks")    # List 3 tasks with descriptions
```

---

## FILE 4: `client.py`

```python
class SREIncidentEnv(EnvClient[SREAction, SREObservation, SREState]):
    def _step_payload(self, action): return action.model_dump()
    def _parse_result(self, payload): obs = SREObservation(**payload.get("observation", payload)); return StepResult(observation=obs, reward=obs.reward, done=obs.done)
    def _parse_state(self, payload): return SREState(**payload)
```

---

## FILE 5: `inference.py`

**System prompt**: Expert SRE Incident Commander. Lists all 5 actions with required fields. Explains incident response protocol (review alerts → query logs → take action → resolve). Demands JSON response format.

**Action parser**: Extracts JSON from markdown code blocks or bare `{...}`, validates `action_type` against allowed Literal values, falls back to text search for action type names.

**Observation formatter**: Structures observation into readable sections: INCIDENT STATUS, ACTIVE ALERTS, SYSTEM METRICS, SERVICES, LOGS, FEEDBACK, HINT.

**Main loop**: For each task (easy, medium, hard):
1. `[START] task=<id> env=sre_incident_commander model=<model>`
2. `reset(task_id=<id>)`, format observation, send to LLM
3. Loop: parse LLM response → `step(action)` → log `[STEP]` → append to conversation
4. `[END] success=<bool> steps=<n> score=<0.000> rewards=<r1,r2,...>`

**Env vars**: `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN` (uses OpenAI client)

---

## FILE 6: `openenv.yaml`

```yaml
name: sre_incident_commander
version: "1.0.0"
description: "AI agent training environment for SRE incident response..."
tasks: [easy (Traffic Spike), medium (Poison Pill), hard (Cascading Lock)]
observation_space: {active_alerts, system_metrics, queried_logs, cloud_cost_usd, uptime_percentage, services, feedback, hint, ...}
action_space: {action_type (Literal 5 types), service_name, replicas, version, query_id}
reward: {continuous, per-step shaped, [-0.50, 0.60], normalized episode score 0.0-1.0}
```

---

## FILE 7: `requirements.txt`

```
openenv-core
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
websockets>=12.0
pydantic>=2.0.0
openai>=1.0.0
httpx>=0.25.0
```

---

## FILE 8: `Dockerfile`

```dockerfile
FROM python:3.11-slim
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
ENV PORT=7860 HOST=0.0.0.0 WORKERS=4 MAX_CONCURRENT_ENVS=100 PYTHONPATH=/app
EXPOSE 7860
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')" || exit 1
CMD ["sh", "-c", "uvicorn server.app:app --host ${HOST} --port ${PORT} --workers ${WORKERS}"]
```

---

## Reward Summary Table

| Task | Action | Reward | Notes |
|------|--------|--------|-------|
| Easy | scale_service(worker-node, >current) | +0.2 | Must increase replicas |
| Easy | queue cleared (<50 auto) | +0.2 | Auto-resolve trigger |
| Easy | wrong action / irrelevant | -0.1 | |
| Easy | queue > 80% capacity | -0.1 | Per-step penalty |
| Medium | query_logs(api-gateway) 1st time | +0.4 | Diagnostic step |
| Medium | rollback(api-gateway, v2.0.9) | +0.6 | Fixes root cause |
| Medium | scale_service(api-gateway) | **-0.5** | Critical mistake |
| Hard | query_logs(api-gateway) 1st | +0.1 | Chain step 1/3 |
| Hard | query_logs(worker-node) 1st | +0.1 | Chain step 2/3 |
| Hard | query_logs(database) 1st | +0.1 | Chain step 3/3 |
| Hard | kill_query(4287) | +0.4 | Root cause fix |
| Hard | scale_service(worker-node, ≥4) post-kill | +0.3 | Stabilize |
| Hard | scale before kill | -0.1 | Wrong order |

---

## Edge Cases

1. **Invalid action_type**: Pydantic Literal validation rejects. `else` branch returns -0.05.
2. **Missing service_name**: Defaults to "". Each handler checks and suggests valid services.
3. **Repeated actions**: Re-query logs → 0.0 reward, "(Already reviewed)". Re-scale → 0.0.
4. **Wrong order (Task 3)**: Scale before kill → -0.1, "workers will also get stuck".
5. **Max steps exceeded**: Forces `done=True`, "Max steps reached."
6. **Premature resolve_incident**: Negative reward with specific condition explanation.
7. **Task 1 queue overflow (≥1000)**: Extra -0.1 penalty, messages "dropped", capped at 1000.
8. **Task 2 wrong version**: -0.1, "last stable is v2.0.9".
9. **Task 3 wrong PID (4290)**: -0.05, "that's a waiting query, not the lock holder."
10. **Scaling to 0/negative**: Handled by `replicas <= current` check → -0.1.

---

## Implementation Order

1. `server/__init__.py` — empty
2. `models.py` — Pydantic types
3. `server/environment.py` — core logic (~500 lines, largest file)
4. `server/app.py` — FastAPI wiring (~40 lines)
5. `client.py` — EnvClient subclass (~20 lines)
6. `openenv.yaml` — manifest
7. `requirements.txt` — dependencies
8. `Dockerfile` — container
9. `inference.py` — baseline agent (~250 lines)
10. `README.md` — documentation

---

## Verification Checklist

- [ ] `pip install -r requirements.txt` succeeds
- [ ] `uvicorn server.app:app --port 7860` starts → `curl localhost:7860/health` returns 200
- [ ] `POST /reset {"task_id": "easy"}` returns valid SREObservation with 2 alerts
- [ ] `POST /step {"action_type": "scale_service", "service_name": "worker-node", "replicas": 5}` returns reward ≈ 0.2
- [ ] `GET /state` returns SREState with step_count incremented
- [ ] All 3 tasks produce grader scores in 0.0-1.0 range
- [ ] Optimal play yields score ~1.0 for all 3 tasks
- [ ] `openenv validate` passes
- [ ] `docker build -t sre-incident-env .` succeeds
- [ ] `docker run -p 7860:7860 sre-incident-env` passes healthcheck
- [ ] `HF_TOKEN=xxx python inference.py` completes <20 min, emits `[START]/[STEP]/[END]`
