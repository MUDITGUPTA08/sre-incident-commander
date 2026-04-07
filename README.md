---
title: SRE Incident Commander
emoji: 🚨
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 7860
tags:
  - openenv
---

# SRE Incident Commander — OpenEnv Environment

An AI agent training environment for **SRE incident response**. The agent acts as Incident Commander, diagnosing and resolving production infrastructure incidents using mock services, metrics, alerts, and logs.

## Why SRE Incident Response?

- Genuine real-world task performed daily at every tech company
- Balances diagnostic reasoning (log analysis) with sequential decision-making (action ordering)
- Natural difficulty progression: simple scaling → diagnosis + rollback → memory leak triage → cascading failure → mTLS cert rotation
- Red herrings and trap actions that punish shallow reasoning (e.g., scaling a leaking service, rolling back a deploy that wasn't the cause)
- All infrastructure mocked via Python dicts/state machines — zero external dependencies, runs on 2 vCPU / 8 GB RAM
- Novel domain not yet seen in the OpenEnv ecosystem

## Tasks

| ID | Name | Difficulty | Optimal Steps | Description |
|----|------|------------|---------------|-------------|
| `easy` | The Traffic Spike | Easy | 3 | Scale workers to drain a growing message queue before it overflows |
| `medium` | The Poison Pill | Medium | 2 | Diagnose a bad deployment (v2.1.0) via logs, then rollback to v2.0.9 |
| `memory_leak` | The Silent OOM | Medium-Hard | 3 | Identify an unbounded ProductCatalogCache causing OOM kills, restart to mitigate, rollback to remove the leak |
| `hard` | The Cascading Lock | Hard | 5 | Navigate red herrings (config change, cache spike), follow a 3-service diagnostic chain, kill a DB lock, then scale to recover |
| `cert_expiry` | The Midnight Expiry | Expert | 7 | Trace TLS failures across 6 services past red herrings (recent deploy, CPU spike), find expired mTLS cert, rotate certs, restart 3 services |
| `perfect_storm` | The Perfect Storm | Nightmare | 6 | Two simultaneous incidents: bad deploy + DB connection leak. Triage correctly — fix customer-facing errors first, then resolve DB leak, then clear backlog |

## Action Space

| Action | Fields | Description |
|--------|--------|-------------|
| `query_logs` | `service_name` | Retrieve logs from a service to diagnose issues |
| `scale_service` | `service_name`, `replicas` | Scale a service's replica count up or down |
| `rollback_deployment` | `service_name`, `version` | Roll back a service to a previous version |
| `kill_query` | `query_id` | Kill a database query/process by PID |
| `restart_service` | `service_name` | Rolling restart of all pods for a service |
| `rotate_certs` | — | Rotate mTLS certificates in the service mesh |
| `resolve_incident` | — | Declare the incident resolved |

## Observation Space

Each observation includes:
- `active_alerts` — List of alerts with severity, service, and message
- `system_metrics` — CPU, memory, queue depth, error rate, latency, DB connections
- `services` — Status of each service (replicas, CPU, version, error rate, etc.)
- `feedback` — Textual feedback on the last action taken
- `hint` — Progressive hint if the agent is stuck
- `cloud_cost_usd` / `uptime_percentage` — Ongoing cost and uptime tracking

## Reward Design

Shaped per-step rewards guide the agent toward optimal incident response:

| Task | Key Rewards | Key Penalties |
|------|-------------|---------------|
| Easy | +0.2 for scaling workers, +0.2 when queue drains | -0.1 wrong action, -0.1 queue > 80% |
| Medium | +0.4 for querying logs, +0.6 for correct rollback | **-0.5** for scaling a broken service (trap!) |
| Memory Leak | +0.3 diagnose leak, +0.1 restart, +0.5 rollback | **-0.15** for scaling a leaking service (trap!) |
| Hard | +0.1 per diagnostic step (×3), +0.4 kill lock, +0.3 scale | -0.15 rollback red herring, -0.1 scaling before kill |
| Cert Expiry | +0.2 find root cause, +0.3 rotate certs, +0.1 per restart | **-0.15** for rolling back a deploy that wasn't the cause |
| Perfect Storm | +0.3 rollback deploy, +0.2 kill leak, +0.1 diagnose/scale | **-0.15** wrong triage order (fixing DB before rollback) |

Episode scores are normalized to `[0.0, 1.0]` by dividing cumulative reward by the maximum achievable.

## Baseline Scores

**Optimal play** (deterministic, hand-crafted agent):

| Task | Steps | Score |
|------|-------|-------|
| Easy | 3 | 1.000 |
| Medium | 2 | 1.000 |
| Memory Leak | 3 | 1.000 |
| Hard | 5 | 1.000 |
| Cert Expiry | 7 | 1.000 |
| Perfect Storm | 6 | 1.000 |

**LLM baseline** (`meta-llama/Llama-3.3-70B-Instruct` via HuggingFace Inference API):

| Task | Steps | Score |
|------|-------|-------|
| Easy | 4 | 1.00 |
| Medium | 2 | 1.00 |
| Hard | 4 | 0.97 |
| Memory Leak | 2 | 0.97 |
| Cert Expiry | 5 | 0.97 |
| Perfect Storm | 5 | 0.95 |

*Scores vary by run due to surface randomization. Tested with Llama 3.3 70B via Groq. Average score: 0.978 across all 6 tasks.*

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `API_BASE_URL` | LLM API endpoint | `https://router.huggingface.co/v1` |
| `MODEL_NAME` | Model identifier for inference | `meta-llama/Llama-3.3-70B-Instruct` |
| `HF_TOKEN` / `OPENAI_API_KEY` | API key for LLM calls | — |
| `ENV_URL` | Environment server URL | `http://localhost:7860` |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn server.app:app --port 7860

# In another terminal, run the baseline agent
HF_TOKEN=your_token ENV_URL=http://localhost:7860 python inference.py
```

## Docker

```bash
docker build -t sre-incident-env .
docker run -p 7860:7860 sre-incident-env
```

## API Endpoints

- `GET /` — Service info
- `GET /health` — Health check
- `GET /tasks` — List available tasks with descriptions
- `POST /reset` — Reset environment (`{"task_id": "easy|medium|memory_leak|hard|cert_expiry|perfect_storm"}`)
- `POST /step` — Take an action (`{"action": {"action_type": "...", ...}}`)
- `GET /state` — Get current environment state
- `WebSocket /ws` — Stateful session (used by EnvClient)

## Architecture

```
models.py              # SREAction, SREObservation, SREState (Pydantic)
client.py              # EnvClient subclass (WebSocket)
inference.py           # Baseline LLM agent with [START]/[STEP]/[END] logging
server/
  __init__.py          # Package marker
  app.py               # FastAPI + create_fastapi_app()
  environment.py       # Core: mock infra, state machines, 6 tasks, graders
```

All infrastructure is mocked via Python dicts and state machines. Each task is a finite state machine with deterministic transitions. No external services, databases, or network calls required.

## Curriculum Learning Support

The environment supports **surface randomization** for curriculum learning via the `noise_level` parameter:

```python
# Deterministic (for debugging/testing)
await env.reset(task_id="hard", noise_level=0.0)

# Light randomization (default)
await env.reset(task_id="hard", noise_level=0.3)

# Full randomization (for training — different PIDs, metrics, request IDs each episode)
await env.reset(task_id="hard", noise_level=1.0, seed=42)
```

Randomization varies surface details (PIDs, CPU/memory values, request/trace IDs, queue depths) while preserving the logical structure. This prevents agents from memorizing fixed answers and enables genuine generalization.

## Efficiency Scoring

The environment rewards efficient incident resolution. Solving a task in fewer steps earns up to a 10% bonus on top of the base score, incentivizing agents to reason efficiently rather than exhaustively exploring.

## Log Realism

Logs are designed to mirror real production environments:
- ISO 8601 timestamps (`[2026-04-05T08:30:15Z]`)
- Request and trace IDs (`req_id=e7a21 trace_id=abc-001`)
- Java/Python stack traces with real class/method names
- Kubernetes container metadata (`container=worker-node-3 reason=OOMKilled exitCode=137`)
- Red herring entries that test the agent's ability to filter noise from signal
- 8–15 log lines per service, with progressive detail levels (INFO → WARN → ERROR → CRITICAL)
