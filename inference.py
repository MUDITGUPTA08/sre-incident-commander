"""Baseline LLM agent for the SRE Incident Commander environment.

Uses an OpenAI-compatible API to drive incident response across all three
tasks, emitting [START]/[STEP]/[END] log lines for the evaluation harness.
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
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:7860")
MODEL_NAME = os.environ.get("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

TASKS = ["easy", "medium", "hard"]

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

5. **resolve_incident** — Declare the incident resolved.
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
# Action parser
# ---------------------------------------------------------------------------

VALID_ACTIONS = {
    "scale_service",
    "rollback_deployment",
    "query_logs",
    "kill_query",
    "resolve_incident",
}


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

    # Fallback: search for action type name in text
    for action_type in VALID_ACTIONS:
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

    parts.append(f"=== INCIDENT STATUS ===")
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


async def run_task(
    task_id: str,
    llm: OpenAI,
    model: str,
) -> Dict[str, Any]:
    """Run a single task episode and return results."""
    print(f"[START] task={task_id} env=sre_incident_commander model={model}")

    async with SREIncidentEnv(base_url=API_BASE_URL) as env:
        result = await env.reset(task_id=task_id)
        obs = result.observation

        conversation: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": format_observation(obs)},
        ]

        rewards: List[float] = []
        steps = 0
        success = False

        while not obs.done:
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
                print(f"  [ERROR] LLM call failed: {e}", file=sys.stderr)
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
            r = obs.reward if obs.reward is not None else 0.0
            rewards.append(r)

            score = obs.metadata.get("score", 0.0) if obs.metadata else 0.0
            print(
                f"[STEP] task={task_id} step={steps} "
                f"action={action.action_type} reward={r:.3f} "
                f"score={score:.3f} done={obs.done}"
            )

            # Add observation to conversation
            conversation.append(
                {"role": "user", "content": format_observation(obs)}
            )

        final_score = obs.metadata.get("score", 0.0) if obs.metadata else 0.0
        success = final_score >= 0.5
        rewards_str = ",".join(f"{r:.3f}" for r in rewards)

        print(
            f"[END] task={task_id} success={success} steps={steps} "
            f"score={final_score:.3f} rewards={rewards_str}"
        )

        return {
            "task_id": task_id,
            "success": success,
            "steps": steps,
            "score": final_score,
            "rewards": rewards,
        }


async def main():
    # Build LLM client
    llm = OpenAI(
        base_url=(
            "https://router.huggingface.co/together/v1"
            if not os.environ.get("OPENAI_BASE_URL")
            else os.environ["OPENAI_BASE_URL"]
        ),
        api_key=HF_TOKEN or os.environ.get("OPENAI_API_KEY", ""),
    )
    model = MODEL_NAME

    print(f"SRE Incident Commander — Baseline Agent")
    print(f"Model: {model}")
    print(f"Environment: {API_BASE_URL}")
    print("=" * 60)

    results = []
    for task_id in TASKS:
        try:
            result = await run_task(task_id, llm, model)
            results.append(result)
        except Exception as e:
            print(f"[END] task={task_id} success=False steps=0 score=0.000 rewards= error={e}")
            results.append({"task_id": task_id, "success": False, "score": 0.0})

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        status = "PASS" if r.get("success") else "FAIL"
        print(f"  {r['task_id']:8s}  {status}  score={r.get('score', 0):.3f}")

    avg = sum(r.get("score", 0) for r in results) / max(len(results), 1)
    print(f"\n  Average score: {avg:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
