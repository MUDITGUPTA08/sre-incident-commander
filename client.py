"""EnvClient subclass for the SRE Incident Commander environment."""

from typing import Any, Dict

from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult

from models import SREAction, SREObservation, SREState


class SREIncidentEnv(EnvClient[SREAction, SREObservation, SREState]):
    """Async WebSocket client for the SRE Incident Commander environment."""

    def _step_payload(self, action: SREAction) -> Dict[str, Any]:
        return action.model_dump()

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[SREObservation]:
        obs_data = payload.get("observation", payload)
        obs = SREObservation(**obs_data)
        reward = payload.get("reward", obs.reward)
        done = payload.get("done", obs.done)
        return StepResult(observation=obs, reward=reward, done=done)

    def _parse_state(self, payload: Dict[str, Any]) -> SREState:
        return SREState(**payload)
