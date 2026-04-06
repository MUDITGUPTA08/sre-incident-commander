"""FastAPI application wiring for SRE Incident Commander environment."""

from fastapi import FastAPI
from openenv.core.env_server import create_fastapi_app

try:
    from ..models import SREAction, SREObservation
except ImportError:
    from models import SREAction, SREObservation

try:
    from .environment import SREIncidentEnvironment, TASK_CONFIGS
except ImportError:
    from environment import SREIncidentEnvironment, TASK_CONFIGS

app = create_fastapi_app(
    env=SREIncidentEnvironment,
    action_cls=SREAction,
    observation_cls=SREObservation,
    max_concurrent_envs=10,
)


@app.get("/")
def root():
    return {
        "name": "sre_incident_commander",
        "version": "1.0.0",
        "description": (
            "AI agent training environment for SRE incident response. "
            "Diagnose and resolve production infrastructure incidents."
        ),
        "tasks": len(TASK_CONFIGS),
        "endpoints": ["/health", "/tasks", "/reset", "/step", "/state"],
    }


@app.get("/tasks")
def list_tasks():
    return [
        {
            "id": cfg["id"],
            "name": cfg["name"],
            "difficulty": cfg["difficulty"],
            "description": cfg["description"],
            "max_attempts": cfg["max_attempts"],
        }
        for cfg in TASK_CONFIGS.values()
    ]


def main(host: str = "0.0.0.0", port: int = 7860):
    """Entry point for uv run or python -m."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
