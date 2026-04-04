"""SRE Incident Commander — core environment logic.

Implements three incident scenarios with mock infrastructure, state machines,
and shaped reward signals. No external dependencies beyond Python stdlib.
"""

import copy
import uuid
from typing import Any, Dict, List, Optional

from openenv.core.env_server import Environment

try:
    from ..models import SREAction, SREObservation, SREState
except ImportError:
    from models import SREAction, SREObservation, SREState


# ---------------------------------------------------------------------------
# Task configuration constants
# ---------------------------------------------------------------------------

TASK_CONFIGS: Dict[str, Dict[str, Any]] = {
    "easy": {
        "id": "easy",
        "name": "The Traffic Spike",
        "difficulty": "easy",
        "description": (
            "Worker-node CPU is at 92% and the order-processing queue has a "
            "backlog of 500 messages growing at 200/min. Scale workers to "
            "drain the queue before it overflows."
        ),
        "max_attempts": 10,
        "alerts": [
            {
                "severity": "critical",
                "service": "order-processing-queue",
                "message": "SQS queue backlog critical: 500 messages pending",
            },
            {
                "severity": "warning",
                "service": "worker-node",
                "message": "High CPU utilisation: 92%",
            },
        ],
        "services": {
            "api-gateway": {"status": "healthy", "replicas": 3, "cpu": 45.0},
            "worker-node": {
                "status": "degraded",
                "replicas": 2,
                "cpu": 92.0,
                "version": "v1.4.0",
            },
            "order-processing-queue": {
                "status": "backlogged",
                "queue_length": 500,
                "growth_rate": "+200/min",
            },
            "database": {"status": "healthy", "connections": 45},
        },
        "metrics": {
            "cpu_percent": 92.0,
            "memory_percent": 68.0,
            "queue_depth": 500,
            "error_rate_percent": 2.1,
            "latency_p99_ms": 450,
            "db_connections": 45,
        },
        "logs": {
            "worker-node": (
                "[ERROR] OOMKill detected on worker-node-2 — pod restarted\n"
                "[WARN]  worker-node-1 CPU at 92%, throttling requests\n"
                "[INFO]  Current replicas: 2. Recommended: scale to 5+ replicas "
                "to handle sustained load\n"
                "[ERROR] Request queue backing up — consumer lag increasing"
            ),
            "order-processing-queue": (
                "[WARN]  Queue depth: 500 messages, growth rate +200/min\n"
                "[INFO]  Consumer throughput: ~200 msg/min (2 workers × 100 msg/worker)\n"
                "[ALERT] At current growth rate, queue will overflow (1000 cap) in ~2.5 min"
            ),
        },
        "deployment_version": "v1.4.0",
    },
    "medium": {
        "id": "medium",
        "name": "The Poison Pill",
        "difficulty": "medium",
        "description": (
            "API error rate spiked to 15% immediately after deployment v2.1.0. "
            "Diagnose the root cause and take corrective action."
        ),
        "max_attempts": 10,
        "alerts": [
            {
                "severity": "critical",
                "service": "api-gateway",
                "message": "API error rate spike: 15% of requests returning 500",
            },
            {
                "severity": "info",
                "service": "api-gateway",
                "message": "Deployment completed: v2.1.0 rolled out to all pods",
            },
        ],
        "services": {
            "api-gateway": {
                "status": "degraded",
                "replicas": 4,
                "cpu": 55.0,
                "version": "v2.1.0",
                "error_rate": 15.0,
            },
            "worker-node": {"status": "healthy", "replicas": 3, "cpu": 30.0},
            "database": {"status": "healthy", "connections": 60},
            "cache-layer": {"status": "healthy", "hit_rate": 85.0},
        },
        "metrics": {
            "cpu_percent": 55.0,
            "memory_percent": 52.0,
            "queue_depth": 20,
            "error_rate_percent": 15.0,
            "latency_p99_ms": 1200,
            "db_connections": 60,
        },
        "logs": {
            "api-gateway": (
                "[ERROR] NullPointerException in PaymentHandler.processOrder() "
                "— introduced in v2.1.0\n"
                "[ERROR] 15% of requests hitting null reference in new payment "
                "validation path\n"
                "[INFO]  v2.1.0 deployed 45 minutes ago. Rollback candidate: "
                "v2.0.9 (last stable)\n"
                "[WARN]  Error rate climbing: 15% and rising — customer impact "
                "confirmed"
            ),
            "worker-node": (
                "[INFO]  Worker-node processing normally\n"
                "[INFO]  No errors detected in worker pipeline"
            ),
            "database": (
                "[INFO]  Database connections stable at 60/200\n"
                "[INFO]  Query latency normal"
            ),
        },
        "deployment_version": "v2.1.0",
    },
    "hard": {
        "id": "hard",
        "name": "The Cascading Lock",
        "difficulty": "hard",
        "description": (
            "Multiple services are failing. API gateway returning 504s, "
            "workers in CrashLoopBackOff, database connection pool nearly "
            "exhausted. Find the root cause and resolve the cascading failure."
        ),
        "max_attempts": 15,
        "alerts": [
            {
                "severity": "critical",
                "service": "api-gateway",
                "message": "API gateway timeout: 40% of requests returning 504",
            },
            {
                "severity": "critical",
                "service": "worker-node",
                "message": (
                    "Worker pods unresponsive: 3/4 in CrashLoopBackOff"
                ),
            },
            {
                "severity": "warning",
                "service": "database",
                "message": "Connection pool near exhaustion: 195/200 connections in use",
            },
        ],
        "services": {
            "api-gateway": {
                "status": "critical",
                "replicas": 4,
                "cpu": 70.0,
                "version": "v3.2.1",
                "error_rate": 40.0,
            },
            "worker-node": {
                "status": "critical",
                "replicas": 4,
                "healthy_replicas": 1,
                "cpu": 98.0,
                "version": "v3.2.1",
            },
            "database": {
                "status": "degraded",
                "connections": 195,
                "max_connections": 200,
                "locked_queries": [
                    {
                        "pid": "4287",
                        "state": "LOCKED",
                        "query": "UPDATE orders SET status='processing' WHERE ...",
                        "duration": "45m",
                        "blocking": True,
                    },
                    {
                        "pid": "4290",
                        "state": "WAITING",
                        "query": "SELECT * FROM orders WHERE ...",
                        "duration": "30m",
                        "blocking": False,
                    },
                ],
            },
            "cache-layer": {
                "status": "degraded",
                "hit_rate": 12.0,
            },
        },
        "metrics": {
            "cpu_percent": 98.0,
            "memory_percent": 85.0,
            "queue_depth": 800,
            "error_rate_percent": 40.0,
            "latency_p99_ms": 8500,
            "db_connections": 195,
        },
        "logs": {
            "api-gateway": (
                "[ERROR] 504 Gateway Timeout — upstream worker-node not "
                "responding\n"
                "[ERROR] 40% of requests failing with timeout after 30s\n"
                "[WARN]  Connection pool to worker-node saturated\n"
                "[INFO]  Investigate worker-node health — check worker-node logs"
            ),
            "worker-node": (
                "[ERROR] 3/4 pods in CrashLoopBackOff — OOMKilled\n"
                "[ERROR] Remaining pod timing out on database queries\n"
                "[WARN]  All DB queries hanging >30s — likely database lock\n"
                "[INFO]  Root cause likely in database layer — check database logs"
            ),
            "database": (
                "[CRITICAL] Long-running query PID 4287 holding exclusive lock "
                "for 45 minutes\n"
                "[ERROR] Connection pool at 195/200 — new connections rejected\n"
                "[WARN]  PID 4287 blocking 47 other queries — cascade risk\n"
                "[INFO]  ACTION REQUIRED: Kill PID 4287 to release lock. "
                "Command: kill_query(query_id='4287')"
            ),
        },
        "deployment_version": "v3.2.1",
    },
}


# ---------------------------------------------------------------------------
# Internal mutable task state (not Pydantic — plain class)
# ---------------------------------------------------------------------------


class _TaskState:
    """Per-episode mutable state that tracks the simulation."""

    def __init__(self, task_id: str) -> None:
        cfg = TASK_CONFIGS[task_id]
        self.task_id = task_id
        self.difficulty = cfg["difficulty"]
        self.alerts: List[Dict[str, Any]] = copy.deepcopy(cfg["alerts"])
        self.services: Dict[str, Any] = copy.deepcopy(cfg["services"])
        self.metrics: Dict[str, Any] = copy.deepcopy(cfg["metrics"])
        self.logs: Dict[str, str] = copy.deepcopy(cfg["logs"])
        self.deployment_version: str = cfg["deployment_version"]
        self.max_attempts: int = cfg["max_attempts"]

        self.step_count: int = 0
        self.cumulative_reward: float = 0.0
        self.cloud_cost: float = 0.0
        self.downtime_minutes: float = 0.0
        self.uptime: float = 100.0
        self.actions_taken: List[str] = []
        self.done: bool = False

        # Task-specific flags ------------------------------------------------
        # Task 1
        self.queue_length: int = cfg["metrics"].get("queue_depth", 0)
        self.worker_replicas: int = (
            cfg["services"].get("worker-node", {}).get("replicas", 2)
        )

        # Task 2
        self.has_queried_logs: bool = False
        self.has_rolled_back: bool = False
        self.scaled_broken_service: bool = False

        # Task 3
        self.queried_api_gateway_logs: bool = False
        self.queried_worker_logs: bool = False
        self.queried_db_logs: bool = False
        self.identified_pid: bool = False
        self.killed_query: bool = False
        self.stabilized: bool = False


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

_MAX_REWARDS = {"easy": 0.4, "medium": 1.0, "hard": 1.0}


def _normalised_score(difficulty: str, cumulative: float) -> float:
    mx = _MAX_REWARDS.get(difficulty, 1.0)
    return max(0.0, min(cumulative / mx, 1.0))


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class SREIncidentEnvironment(Environment[SREAction, SREObservation, SREState]):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ts: Optional[_TaskState] = None
        self._episode_id: Optional[str] = None

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SREObservation:
        task_id = kwargs.get("task_id", "easy")
        if task_id not in TASK_CONFIGS:
            task_id = "easy"

        self._episode_id = episode_id or str(uuid.uuid4())
        self._ts = _TaskState(task_id)

        return self._build_observation(
            reward=None,
            feedback=f"Incident opened: {TASK_CONFIGS[task_id]['name']}. "
            f"{TASK_CONFIGS[task_id]['description']}",
            hint="Review the active alerts and system metrics, then decide on your first action.",
        )

    # ------------------------------------------------------------------
    # step
    # ------------------------------------------------------------------

    def step(
        self,
        action: SREAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> SREObservation:
        ts = self._ts
        if ts is None:
            return SREObservation(
                done=True,
                reward=0.0,
                feedback="Environment not initialised. Call reset() first.",
            )
        if ts.done:
            return self._build_observation(
                reward=0.0,
                feedback="Incident already closed. Call reset() for a new episode.",
            )

        ts.step_count += 1
        ts.cloud_cost += 0.50
        ts.downtime_minutes += 1.0
        ts.actions_taken.append(action.action_type)

        # Dispatch to the appropriate task handler
        handler = {
            "easy": self._step_easy,
            "medium": self._step_medium,
            "hard": self._step_hard,
        }.get(ts.task_id, self._step_easy)

        reward, feedback, hint = handler(action)

        ts.cumulative_reward += reward

        # Check max attempts
        if not ts.done and ts.step_count >= ts.max_attempts:
            ts.done = True
            feedback += " Max steps reached — incident auto-closed."

        return self._build_observation(reward=reward, feedback=feedback, hint=hint)

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    @property
    def state(self) -> SREState:
        ts = self._ts
        if ts is None:
            return SREState(episode_id=self._episode_id)
        return SREState(
            episode_id=self._episode_id,
            step_count=ts.step_count,
            task_id=ts.task_id,
            difficulty=ts.difficulty,
            current_score=_normalised_score(ts.difficulty, ts.cumulative_reward),
            total_downtime_minutes=ts.downtime_minutes,
            total_cost_usd=ts.cloud_cost,
            actions_taken=list(ts.actions_taken),
            completed=ts.done,
        )

    # ==================================================================
    # Task 1 — The Traffic Spike
    # ==================================================================

    def _step_easy(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # --- Queue dynamics (applied before action processing) ---
        growth = 200
        drain = ts.worker_replicas * 100
        ts.queue_length = max(0, ts.queue_length + growth - drain)

        at = action.action_type

        if at == "scale_service":
            if action.service_name != "worker-node":
                reward = -0.1
                feedback = (
                    f"'{action.service_name}' is not the bottleneck. "
                    "The worker-node is the service that needs scaling."
                )
            elif action.replicas <= ts.worker_replicas:
                reward = -0.1
                feedback = (
                    f"Replicas must be increased (currently {ts.worker_replicas}). "
                    "Scaling down during an incident is counter-productive."
                )
            else:
                old = ts.worker_replicas
                ts.worker_replicas = action.replicas
                ts.services["worker-node"]["replicas"] = action.replicas
                ts.services["worker-node"]["cpu"] = max(
                    30.0, 92.0 * (2 / max(action.replicas, 1))
                )
                reward = 0.2
                feedback = (
                    f"Scaled worker-node from {old} to {action.replicas} replicas. "
                    f"Drain rate now {action.replicas * 100} msg/min."
                )

        elif at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                feedback = f"Logs for {svc}:\n{ts.logs[svc]}"
            else:
                feedback = f"No logs available for '{svc}'. Valid services: {', '.join(ts.logs.keys())}"

        elif at == "resolve_incident":
            if ts.queue_length >= 50:
                reward = -0.2
                feedback = (
                    f"Cannot resolve — queue still has {ts.queue_length} messages. "
                    "Drain the backlog first."
                )
            else:
                ts.done = True
                feedback = "Incident resolved! Queue fully drained."

        elif at == "rollback_deployment":
            reward = -0.1
            feedback = "No bad deployment detected. This is a scaling issue, not a code issue."

        elif at == "kill_query":
            reward = -0.1
            feedback = "No database lock detected. Focus on scaling the workers."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # --- Post-action queue dynamics ---
        drain = ts.worker_replicas * 100
        ts.queue_length = max(0, ts.queue_length + 0 - 0)  # already applied above

        # Update metrics
        ts.metrics["queue_depth"] = ts.queue_length
        ts.services["order-processing-queue"]["queue_length"] = ts.queue_length

        # Queue overflow penalty
        if ts.queue_length >= 1000:
            reward -= 0.1
            ts.queue_length = 1000
            ts.metrics["queue_depth"] = 1000
            feedback += " CRITICAL: Queue overflow — messages being dropped!"
            if not any(
                a.get("message", "").startswith("Queue overflow")
                for a in ts.alerts
            ):
                ts.alerts.append(
                    {
                        "severity": "critical",
                        "service": "order-processing-queue",
                        "message": "Queue overflow! Messages dropped.",
                    }
                )
        elif ts.queue_length > 800:
            reward -= 0.1
            feedback += f" WARNING: Queue at {ts.queue_length}/1000 — nearing overflow."

        # Auto-resolve check
        if ts.queue_length < 50 and not ts.done:
            reward += 0.2
            ts.done = True
            feedback += " Queue drained successfully — incident auto-resolved!"

        # Hints
        if ts.step_count >= 3 and ts.queue_length >= 500:
            hint = (
                "Hint: The queue is growing because the 2 workers can only "
                "drain 200 msg/min but 200 msg/min are arriving. Scale "
                "worker-node to 5+ replicas."
            )

        ts.uptime = max(90.0, ts.uptime - 0.5)
        return reward, feedback, hint

    # ==================================================================
    # Task 2 — The Poison Pill
    # ==================================================================

    def _step_medium(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # Ongoing degradation while bug is live
        if not ts.has_rolled_back:
            ts.uptime = max(80.0, ts.uptime - 0.3)
            ts.metrics["latency_p99_ms"] = min(
                5000, ts.metrics["latency_p99_ms"] + 200
            )

        at = action.action_type

        if at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                if svc == "api-gateway" and not ts.has_queried_logs:
                    ts.has_queried_logs = True
                    reward = 0.4
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "Root cause identified: NullPointerException in v2.1.0 "
                        "PaymentHandler."
                    )
                else:
                    feedback = f"Logs for {svc}:\n{ts.logs[svc]}\n(Already reviewed)"
            else:
                feedback = (
                    f"No logs available for '{svc}'. "
                    f"Valid services: {', '.join(ts.logs.keys())}"
                )

        elif at == "rollback_deployment":
            if action.service_name != "api-gateway":
                reward = -0.1
                feedback = (
                    f"'{action.service_name}' doesn't need a rollback. "
                    "The api-gateway running v2.1.0 is the problem."
                )
            elif action.version != "v2.0.9":
                reward = -0.1
                feedback = (
                    f"Version '{action.version}' is not correct. "
                    "The last stable version is v2.0.9."
                )
            elif ts.has_rolled_back:
                feedback = "Already rolled back. No further action needed."
            else:
                ts.has_rolled_back = True
                ts.deployment_version = "v2.0.9"
                ts.services["api-gateway"]["version"] = "v2.0.9"
                ts.services["api-gateway"]["status"] = "healthy"
                ts.services["api-gateway"]["error_rate"] = 0.5
                ts.metrics["error_rate_percent"] = 0.5
                ts.metrics["latency_p99_ms"] = 150
                ts.alerts = [
                    a
                    for a in ts.alerts
                    if "error rate" not in a.get("message", "").lower()
                ]
                reward = 0.6
                feedback = (
                    "Rolled back api-gateway from v2.1.0 to v2.0.9. "
                    "Error rate dropped to 0.5%. Incident resolved!"
                )
                ts.done = True

        elif at == "scale_service":
            if action.service_name == "api-gateway":
                ts.scaled_broken_service = True
                reward = -0.5
                feedback = (
                    "CRITICAL MISTAKE: Scaling a service with a code bug just "
                    "multiplies the errors! The issue is in v2.1.0's code, "
                    "not capacity. Consider rolling back instead."
                )
            else:
                reward = -0.1
                feedback = (
                    f"Scaling '{action.service_name}' won't help. "
                    "The error rate is caused by a code bug, not load."
                )

        elif at == "resolve_incident":
            if not ts.has_rolled_back:
                reward = -0.2
                feedback = (
                    "Cannot resolve — error rate is still at "
                    f"{ts.metrics['error_rate_percent']}%. "
                    "The root cause (v2.1.0 bug) has not been addressed."
                )
            else:
                ts.done = True
                feedback = "Incident confirmed resolved."

        elif at == "kill_query":
            reward = -0.1
            feedback = (
                "No database issue detected. This incident is caused by a "
                "bad deployment, not a DB lock."
            )

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Hints
        if ts.step_count >= 2 and not ts.has_queried_logs:
            hint = (
                "Hint: Check the api-gateway logs to understand why the "
                "error rate is 15%."
            )
        elif ts.step_count >= 4 and ts.has_queried_logs and not ts.has_rolled_back:
            hint = (
                "Hint: The logs showed a NullPointerException in v2.1.0. "
                "Roll back api-gateway to v2.0.9."
            )

        return reward, feedback, hint

    # ==================================================================
    # Task 3 — The Cascading Lock
    # ==================================================================

    def _step_hard(self, action: SREAction) -> tuple:
        ts = self._ts
        assert ts is not None
        reward = 0.0
        feedback = ""
        hint = ""

        # Ongoing degradation until lock is killed
        if not ts.killed_query:
            ts.metrics["error_rate_percent"] = min(
                80.0, ts.metrics["error_rate_percent"] + 5.0
            )
            ts.metrics["latency_p99_ms"] = min(
                30000, ts.metrics["latency_p99_ms"] + 2000
            )
            ts.metrics["db_connections"] = min(
                200, ts.metrics["db_connections"] + 2
            )
            ts.uptime = max(60.0, ts.uptime - 1.0)

            if ts.metrics["db_connections"] >= 200:
                if not any(
                    "full block" in a.get("message", "").lower()
                    for a in ts.alerts
                ):
                    ts.alerts.append(
                        {
                            "severity": "critical",
                            "service": "database",
                            "message": (
                                "FULL BLOCK: Connection pool exhausted "
                                "(200/200). All new connections rejected."
                            ),
                        }
                    )

        at = action.action_type

        if at == "query_logs":
            svc = action.service_name
            if svc in ts.logs:
                if svc == "api-gateway" and not ts.queried_api_gateway_logs:
                    ts.queried_api_gateway_logs = True
                    reward = 0.1
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "The api-gateway is timing out on worker-node requests. "
                        "Investigate worker-node next."
                    )
                elif svc == "worker-node" and not ts.queried_worker_logs:
                    ts.queried_worker_logs = True
                    reward = 0.1
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "Workers are timing out on database queries. "
                        "The database layer is the likely root cause."
                    )
                elif svc == "database" and not ts.queried_db_logs:
                    ts.queried_db_logs = True
                    ts.identified_pid = True
                    reward = 0.1
                    feedback = (
                        f"Logs for {svc}:\n{ts.logs[svc]}\n\n"
                        "ROOT CAUSE FOUND: PID 4287 is holding an exclusive "
                        "lock for 45 minutes, blocking 47 other queries. "
                        "Kill this query to release the lock."
                    )
                else:
                    feedback = f"Logs for {svc}:\n{ts.logs[svc]}\n(Already reviewed)"
            else:
                feedback = (
                    f"No logs available for '{svc}'. "
                    f"Valid services: {', '.join(ts.logs.keys())}"
                )

        elif at == "kill_query":
            if ts.killed_query:
                feedback = "Lock already killed. Focus on stabilising the system."
            elif action.query_id == "4287":
                ts.killed_query = True
                reward = 0.4
                # Update system state post-kill
                ts.metrics["db_connections"] = 60
                ts.metrics["error_rate_percent"] = 15.0
                ts.metrics["latency_p99_ms"] = 3000
                ts.services["database"]["connections"] = 60
                ts.services["database"]["locked_queries"] = []
                ts.services["database"]["status"] = "recovering"
                ts.services["worker-node"]["status"] = "recovering"
                ts.services["worker-node"]["healthy_replicas"] = 1
                ts.queue_length = 600
                ts.metrics["queue_depth"] = 600

                # Update alerts
                ts.alerts = [
                    a
                    for a in ts.alerts
                    if "connection pool" not in a.get("message", "").lower()
                ]
                ts.alerts.append(
                    {
                        "severity": "warning",
                        "service": "worker-node",
                        "message": (
                            "Workers recovering but backlog at 600 messages. "
                            "Scale worker-node to >=4 replicas to drain backlog."
                        ),
                    }
                )
                feedback = (
                    "Killed PID 4287 — database lock released! "
                    "Connections dropped to 60/200. Workers recovering but "
                    "there's a backlog of 600 messages. Scale worker-node to "
                    "clear it."
                )
            elif action.query_id == "4290":
                reward = -0.05
                feedback = (
                    "PID 4290 is a waiting query, not the lock holder. "
                    "The blocking lock is held by PID 4287."
                )
            else:
                reward = -0.05
                feedback = (
                    f"PID '{action.query_id}' not found. Check the database "
                    "logs — the blocking PID is 4287."
                )

        elif at == "scale_service":
            if not ts.killed_query:
                reward = -0.1
                feedback = (
                    "Scaling won't help — new workers will also get stuck "
                    "on the database lock. Kill the blocking query (PID 4287) "
                    "first."
                )
            elif action.service_name != "worker-node":
                reward = -0.1
                feedback = (
                    f"'{action.service_name}' doesn't need scaling. "
                    "Scale worker-node to drain the message backlog."
                )
            elif action.replicas < 4:
                reward = -0.1
                feedback = (
                    f"{action.replicas} replicas is not enough to drain the "
                    "backlog. Scale worker-node to at least 4 replicas."
                )
            elif ts.stabilized:
                feedback = "Already scaled. System is stable."
            else:
                ts.stabilized = True
                ts.services["worker-node"]["replicas"] = action.replicas
                ts.services["worker-node"]["status"] = "healthy"
                ts.services["worker-node"]["healthy_replicas"] = action.replicas
                ts.services["worker-node"]["cpu"] = 45.0
                ts.services["api-gateway"]["status"] = "healthy"
                ts.services["api-gateway"]["error_rate"] = 0.5
                ts.services["cache-layer"]["status"] = "healthy"
                ts.services["cache-layer"]["hit_rate"] = 85.0
                ts.metrics["queue_depth"] = 0
                ts.metrics["error_rate_percent"] = 0.5
                ts.metrics["latency_p99_ms"] = 80
                ts.metrics["cpu_percent"] = 45.0
                ts.alerts = []
                reward = 0.3
                feedback = (
                    f"Scaled worker-node to {action.replicas} replicas. "
                    "Backlog cleared, error rate 0.5%, latency 80ms. "
                    "All services healthy — incident resolved!"
                )
                ts.done = True

        elif at == "rollback_deployment":
            reward = -0.1
            feedback = (
                "This is not a deployment issue. The root cause is a "
                "database lock. Investigate the database logs."
            )

        elif at == "resolve_incident":
            if not ts.killed_query:
                reward = -0.2
                feedback = (
                    "Cannot resolve — database lock is still active and "
                    f"error rate is {ts.metrics['error_rate_percent']}%."
                )
            elif not ts.stabilized:
                reward = -0.1
                feedback = (
                    "Lock is cleared but workers are still recovering with "
                    "a backlog of 600 messages. Scale worker-node first."
                )
            else:
                ts.done = True
                feedback = "Incident confirmed resolved."

        else:
            reward = -0.05
            feedback = f"Unknown action type: {at}"

        # Hints
        if not ts.queried_api_gateway_logs and ts.step_count >= 2:
            hint = "Hint: Start by checking api-gateway logs to understand the 504 timeouts."
        elif (
            ts.queried_api_gateway_logs
            and not ts.queried_worker_logs
            and ts.step_count >= 4
        ):
            hint = "Hint: The api-gateway pointed to worker-node issues. Check worker-node logs."
        elif (
            ts.queried_worker_logs
            and not ts.queried_db_logs
            and ts.step_count >= 6
        ):
            hint = "Hint: Workers are stuck on DB queries. Check database logs for locks."
        elif ts.queried_db_logs and not ts.killed_query and ts.step_count >= 8:
            hint = "Hint: PID 4287 is the blocking query. Use kill_query(query_id='4287')."

        return reward, feedback, hint

    # ------------------------------------------------------------------
    # Observation builder
    # ------------------------------------------------------------------

    def _build_observation(
        self,
        reward: Optional[float],
        feedback: str = "",
        hint: str = "",
    ) -> SREObservation:
        ts = self._ts
        if ts is None:
            return SREObservation(done=True, reward=0.0, feedback=feedback)

        cfg = TASK_CONFIGS[ts.task_id]
        return SREObservation(
            done=ts.done,
            reward=reward,
            active_alerts=list(ts.alerts),
            system_metrics=dict(ts.metrics),
            queried_logs="",
            cloud_cost_usd=round(ts.cloud_cost, 2),
            uptime_percentage=round(ts.uptime, 2),
            task_id=ts.task_id,
            difficulty=ts.difficulty,
            feedback=feedback,
            hint=hint,
            current_deployment_version=ts.deployment_version,
            services=copy.deepcopy(ts.services),
            attempt_number=ts.step_count,
            max_attempts=ts.max_attempts,
            metadata={
                "score": _normalised_score(ts.difficulty, ts.cumulative_reward),
                "cumulative_reward": round(ts.cumulative_reward, 4),
            },
        )
