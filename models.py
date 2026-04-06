from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from openenv.core.env_server import Action, Observation, State


class SREAction(Action):
    """Action taken by the SRE Incident Commander agent."""

    action_type: Literal[
        "scale_service",
        "rollback_deployment",
        "query_logs",
        "kill_query",
        "restart_service",
        "rotate_certs",
        "resolve_incident",
    ]
    service_name: str = ""
    replicas: int = 0
    version: str = ""
    query_id: str = ""
    reasoning: str = ""


class SREObservation(Observation):
    """Observation returned to the agent after each action."""

    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    system_metrics: Dict[str, Any] = Field(default_factory=dict)
    queried_logs: str = ""
    cloud_cost_usd: float = 0.0
    uptime_percentage: float = 100.0
    task_id: str = ""
    difficulty: str = ""
    feedback: str = ""
    hint: str = ""
    current_deployment_version: str = ""
    services: Dict[str, Any] = Field(default_factory=dict)
    attempt_number: int = 0
    max_attempts: int = 10


class SREState(State):
    """Internal state exposed via the /state endpoint."""

    task_id: str = ""
    difficulty: str = ""
    current_score: float = 0.0
    total_downtime_minutes: float = 0.0
    total_cost_usd: float = 0.0
    actions_taken: List[str] = Field(default_factory=list)
    completed: bool = False
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
