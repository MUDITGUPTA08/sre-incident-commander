# SRE Incident Commander — OpenEnv Environment

An AI agent training environment for **SRE incident response**. The agent acts as Incident Commander, diagnosing and resolving production infrastructure incidents using mock services, metrics, alerts, and logs.

## Tasks

| ID | Name | Difficulty | Description |
|----|------|------------|-------------|
| `easy` | The Traffic Spike | Easy | Scale workers to drain a growing message queue |
| `medium` | The Poison Pill | Medium | Diagnose a bad deployment via logs and rollback |
| `hard` | The Cascading Lock | Hard | Follow a diagnostic chain through cascading failures, kill a DB lock, then scale to recover |

## Actions

| Action | Fields | Description |
|--------|--------|-------------|
| `query_logs` | `service_name` | Retrieve logs from a service |
| `scale_service` | `service_name`, `replicas` | Scale a service's replica count |
| `rollback_deployment` | `service_name`, `version` | Roll back to a previous version |
| `kill_query` | `query_id` | Kill a database query by PID |
| `resolve_incident` | — | Declare the incident resolved |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn server.app:app --port 7860

# In another terminal, run the baseline agent
HF_TOKEN=your_token python inference.py
```

## Docker

```bash
docker build -t sre-incident-env .
docker run -p 7860:7860 sre-incident-env
```

## API Endpoints

- `GET /` — Service info
- `GET /health` — Health check
- `GET /tasks` — List available tasks
- `POST /reset` — Reset environment (pass `{"task_id": "easy|medium|hard"}`)
- `POST /step` — Take an action
- `GET /state` — Get current environment state

## Scoring

Each task has shaped per-step rewards. The episode score is normalized to `[0.0, 1.0]` by dividing cumulative reward by the maximum achievable reward for that task.

## Architecture

All infrastructure is mocked via Python dicts and state machines — zero external dependencies, runs on 2 vCPU / 8 GB RAM.
