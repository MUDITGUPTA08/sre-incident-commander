"""Baseline LLM agent for the SRE Incident Commander environment.

Uses an OpenAI-compatible API to drive incident response across all five
tasks, emitting [START]/[STEP]/[END] log lines per the mandatory format.
"""

import json
import os
import re
import sys
import asyncio
from typing import Any, Dict, List, Optional

from openai import OpenAI

from client import SREIncidentEnv
from models import SREAction, SREObservation

# ---------------------------------------------------------------------------
# Configuration (mandatory env vars)
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY", "")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "")

# Environment server URL (where the OpenEnv server is running)
ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")
BENCHMARK = "sre_incident_commander"
TASKS = ["easy", "medium", "hard", "memory_leak", "cert_expiry"]
MAX_STEPS = 20

SYSTEM_PROMPT = """\
You are an expert SRE Incident Commander. You are responsible for diagnosing \
and resolving production infrastructure incidents.

## Available Actions

You MUST respond with a single JSON object containing one of these actions:

1. **query_logs** — Retrieve logs from a service.
   ```json
   {"action_type": "query_logs", "service_name": "<service>", "reasoning": "..."}
   ```

2. **scale_service** — Scale a service's replica count.
   ```json
   {"action_type": "scale_service", "service_name": "<service>", "replicas": <int>, "reasoning": "..."}
   ```

3. **rollback_deployment** — Roll back a service to a previous version.
   ```json
   {"action_type": "rollback_deployment", "service_name": "<service>", "version": "<version>", "reasoning": "..."}
   ```

4. **kill_query** — Kill a database query/process by PID.
   ```json
   {"action_type": "kill_query", "query_id": "<pid>", "reasoning": "..."}
   ```

5. **restart_service** — Restart a service (rolling restart of all pods).
   ```json
   {"action_type": "restart_service", "service_name": "<service>", "reasoning": "..."}
   ```

6. **rotate_certs** — Rotate mTLS certificates in the service mesh.
   ```json
   {"action_type": "rotate_certs", "reasoning": "..."}
   ```

7. **resolve_incident** — Declare the incident resolved.
   ```json
   {"action_type": "resolve_incident", "reasoning": "..."}
   ```

## Protocol

1. Review active alerts and system metrics carefully.
2. Query logs to understand root cause BEFORE taking action.
3. Take the most targeted corrective action.
4. Only resolve_incident when all metrics are healthy.

## Response Format

Respond with ONLY a JSON object. No markdown, no explanation outside JSON.
Include a "reasoning" field explaining your thought process.
"""


# ---------------------------------------------------------------------------
# Structured logging (mandatory format)
# ---------------------------------------------------------------------------


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Action parser
# ---------------------------------------------------------------------------

VALID_ACTIONS = {
    "scale_service",
    "rollback_deployment",
    "query_logs",
    "kill_query",
    "restart_service",
    "rotate_certs",
    "resolve_incident",
}

# Ordered by priority for the fallback text parser — diagnostic actions first,
# resolve_incident last so it's only picked when nothing else matches.
_ACTION_PRIORITY = [
    "query_logs",
    "kill_query",
    "rollback_deployment",
    "scale_service",
    "restart_service",
    "rotate_certs",
    "resolve_incident",
]


def parse_action(text: str) -> Optional[SREAction]:
    """Extract an SREAction from LLM output text."""
    # Try JSON in markdown code blocks
    code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_match:
        try:
            data = json.loads(code_match.group(1))
            if data.get("action_type") in VALID_ACTIONS:
                return SREAction(**{k: v for k, v in data.items() if k != "metadata"})
        except (json.JSONDecodeError, Exception):
            pass

    # Try bare JSON object
    json_match = re.search(r"\{[^{}]*\"action_type\"[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if data.get("action_type") in VALID_ACTIONS:
                return SREAction(**{k: v for k, v in data.items() if k != "metadata"})
        except (json.JSONDecodeError, Exception):
            pass

    # Fallback: search for action type name in text (priority order)
    for action_type in _ACTION_PRIORITY:
        if action_type in text.lower():
            return SREAction(
                action_type=action_type,  # type: ignore[arg-type]
                reasoning=f"Fallback parse: found '{action_type}' in response",
            )

    return None


# ---------------------------------------------------------------------------
# Observation formatter
# ---------------------------------------------------------------------------


def format_observation(obs: SREObservation) -> str:
    """Format an SREObservation into a readable prompt section."""
    parts = []

    parts.append("=== INCIDENT STATUS ===")
    parts.append(f"Task: {obs.task_id} ({obs.difficulty})")
    parts.append(f"Step: {obs.attempt_number}/{obs.max_attempts}")
    parts.append(f"Uptime: {obs.uptime_percentage}%  |  Cost: ${obs.cloud_cost_usd}")
    parts.append(f"Deployment: {obs.current_deployment_version}")

    if obs.feedback:
        parts.append(f"\n--- FEEDBACK ---\n{obs.feedback}")

    if obs.active_alerts:
        parts.append("\n--- ACTIVE ALERTS ---")
        for alert in obs.active_alerts:
            sev = alert.get("severity", "info").upper()
            svc = alert.get("service", "unknown")
            msg = alert.get("message", "")
            parts.append(f"  [{sev}] {svc}: {msg}")

    if obs.system_metrics:
        parts.append("\n--- SYSTEM METRICS ---")
        m = obs.system_metrics
        parts.append(f"  CPU: {m.get('cpu_percent', '?')}%")
        parts.append(f"  Memory: {m.get('memory_percent', '?')}%")
        parts.append(f"  Queue Depth: {m.get('queue_depth', '?')}")
        parts.append(f"  Error Rate: {m.get('error_rate_percent', '?')}%")
        parts.append(f"  Latency P99: {m.get('latency_p99_ms', '?')}ms")
        parts.append(f"  DB Connections: {m.get('db_connections', '?')}")

    if obs.services:
        parts.append("\n--- SERVICES ---")
        for name, info in obs.services.items():
            status = info.get("status", "unknown")
            details = {k: v for k, v in info.items() if k != "status"}
            parts.append(f"  {name}: {status}  {details}")

    if obs.hint:
        parts.append(f"\n--- HINT ---\n{obs.hint}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


MAX_CONVERSATION_MESSAGES = 16  # Keep system + last N messages to avoid context overflow


async def run_task(
    task_id: str,
    llm: OpenAI,
    model: str,
    env_url: str,
) -> Dict[str, Any]:
    """Run a single task episode and return results."""
    log_start(task=task_id, env=BENCHMARK, model=model)

    rewards: List[float] = []
    steps = 0
    score = 0.0
    success = False

    try:
        if LOCAL_IMAGE_NAME:
            env = await SREIncidentEnv.from_docker_image(LOCAL_IMAGE_NAME)
        else:
            env = SREIncidentEnv(base_url=env_url)

        async with env:
            result = await env.reset(task_id=task_id)
            obs = result.observation

            conversation: List[Dict[str, str]] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": format_observation(obs)},
            ]

            while not obs.done and steps < MAX_STEPS:
                # Truncate conversation to avoid exceeding LLM context window.
                # Keep the system prompt (index 0) and the most recent messages.
                if len(conversation) > MAX_CONVERSATION_MESSAGES:
                    conversation = [conversation[0]] + conversation[-(MAX_CONVERSATION_MESSAGES - 1):]

                # Get LLM response
                try:
                    response = llm.chat.completions.create(
                        model=model,
                        messages=conversation,
                        temperature=0.1,
                        max_tokens=512,
                    )
                    llm_text = response.choices[0].message.content or ""
                except Exception as e:
                    print(f"[DEBUG] LLM call failed: {e}", file=sys.stderr, flush=True)
                    llm_text = '{"action_type": "resolve_incident", "reasoning": "LLM error fallback"}'

                conversation.append({"role": "assistant", "content": llm_text})

                # Parse action
                action = parse_action(llm_text)
                if action is None:
                    action = SREAction(
                        action_type="resolve_incident",
                        reasoning="Failed to parse action from LLM response",
                    )

                # Execute step
                step_result = await env.step(action)
                obs = step_result.observation
                steps += 1
                r = float(obs.reward) if obs.reward is not None else 0.0
                rewards.append(r)

                # Build action string for logging
                action_str = action.action_type
                params = []
                if action.service_name:
                    params.append(action.service_name)
                if action.replicas:
                    params.append(str(action.replicas))
                if action.version:
                    params.append(action.version)
                if action.query_id:
                    params.append(action.query_id)
                if params:
                    action_str += f"({','.join(params)})"

                log_step(
                    step=steps,
                    action=action_str,
                    reward=r,
                    done=obs.done,
                    error=None,
                )

                # Add observation to conversation
                conversation.append(
                    {"role": "user", "content": format_observation(obs)}
                )

            # The framework strips metadata from WS observations, so
            # fetch the authoritative score from the state endpoint.
            try:
                st = await env.state()
                score = st.current_score
            except Exception:
                score = 0.0
            success = score >= 0.5

    except Exception as e:
        print(f"[DEBUG] Task {task_id} error: {e}", file=sys.stderr, flush=True)

    log_end(success=success, steps=steps, score=score, rewards=rewards)

    return {
        "task_id": task_id,
        "success": success,
        "steps": steps,
        "score": score,
        "rewards": rewards,
    }


def print_summary(results: List[Dict[str, Any]]) -> None:
    """Print a formatted evaluation summary table."""
    print("\n" + "=" * 65, flush=True)
    print("  SRE INCIDENT COMMANDER — EVALUATION SUMMARY", flush=True)
    print("=" * 65, flush=True)
    print(f"  {'Task':<15} {'Steps':>6} {'Score':>8} {'Success':>9}", flush=True)
    print("-" * 65, flush=True)
    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        print(
            f"  {r['task_id']:<15} {r['steps']:>6} {r['score']:>8.3f} {status:>9}",
            flush=True,
        )
    print("-" * 65, flush=True)
    avg_score = sum(r["score"] for r in results) / len(results) if results else 0.0
    total_pass = sum(1 for r in results if r["success"])
    print(
        f"  {'AVERAGE':<15} {'':>6} {avg_score:>8.3f} {total_pass}/{len(results):>7}",
        flush=True,
    )
    print("=" * 65, flush=True)


async def main():
    llm = OpenAI(
        base_url=API_BASE_URL,
        api_key=HF_TOKEN,
    )
    model = MODEL_NAME

    results = []
    for task_id in TASKS:
        result = await run_task(task_id, llm, model, ENV_URL)
        results.append(result)

    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
