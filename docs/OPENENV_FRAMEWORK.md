# OpenEnv Framework Reference

## What Is OpenEnv?

OpenEnv is a standardized framework for building RL environments that AI agents can learn from. Created by Meta, it provides:

- Standard 3-method interface: `reset()`, `step()`, `state()`
- Type-safe Pydantic models for actions, observations, and state
- Client-server architecture with WebSocket persistence
- Docker containerization for deployment
- CLI tools for scaffolding, validation, and deployment

**GitHub**: https://github.com/meta-pytorch/OpenEnv
**Docs**: https://meta-pytorch.org/OpenEnv/
**Course**: https://github.com/huggingface/openenv-course
**HF Org**: https://huggingface.co/openenv

---

## Base Classes

### Action (Pydantic BaseModel, extra="forbid")

```python
class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### Observation (Pydantic BaseModel, extra="forbid")

```python
class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    done: bool = Field(default=False)
    reward: bool | int | float | None = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### State (Pydantic BaseModel, extra="allow")

```python
class State(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)
    episode_id: Optional[str] = Field(default=None)
    step_count: int = Field(default=0, ge=0)
```

### Environment (ABC, Generic[ActT, ObsT, StateT])

```python
class Environment(ABC, Generic[ActT, ObsT, StateT]):
    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def __init__(self, transform=None, rubric=None): ...

    @abstractmethod
    def reset(self, seed=None, episode_id=None, **kwargs) -> ObsT: ...

    @abstractmethod
    def step(self, action: ActT, timeout_s=None, **kwargs) -> ObsT: ...

    @property
    @abstractmethod
    def state(self) -> StateT: ...

    def get_metadata(self) -> EnvironmentMetadata: ...
    def close(self) -> None: ...
```

### EnvClient (ABC, Generic[ActT, ObsT, StateT])

```python
class EnvClient(ABC, Generic[ActT, ObsT, StateT]):
    def __init__(self, base_url, connect_timeout_s=10.0, ...): ...

    @abstractmethod
    def _step_payload(self, action: ActT) -> Dict[str, Any]: ...

    @abstractmethod
    def _parse_result(self, payload) -> StepResult[ObsT]: ...

    @abstractmethod
    def _parse_state(self, payload) -> StateT: ...

    async def reset(self, **kwargs) -> StepResult[ObsT]: ...
    async def step(self, action, **kwargs) -> StepResult[ObsT]: ...
    async def state(self) -> StateT: ...
```

### create_fastapi_app

```python
def create_fastapi_app(
    env: Callable[[], Environment],
    action_cls: Type[Action],
    observation_cls: Type[Observation],
    max_concurrent_envs: Optional[int] = None,
) -> FastAPI:
```

---

## CLI Commands

```bash
openenv init <name>       # Scaffold new environment
openenv validate           # Validate project structure
openenv push [--repo-id]  # Deploy to HF Spaces
```

---

## Validation Requirements (`openenv validate`)

All must pass:

1. `openenv.yaml` exists
2. `pyproject.toml` exists and is parseable
3. `uv.lock` exists
4. `[project.scripts]` has `server` entry referencing `:main`
5. `[project]` dependencies include `openenv-core>=0.2.0` or `openenv>=0.2.0`
6. `server/app.py` exists
7. `server/app.py` contains `def main(` function
8. `server/app.py` contains `if __name__ == "__main__"` and `main()` call

---

## Reference Environments

| Environment | Purpose |
|---|---|
| **Echo** | Testing infrastructure; echoes messages |
| **Coding** | Sandboxed Python execution |
| **Chess** | Full chess rules with configurable opponents |
| **Atari** | Classic arcade learning benchmarks |
| **FinRL** | Financial market simulations |

---

## Dual-Import Pattern (Critical for Docker)

```python
try:
    from ..models import SREAction
except ImportError:
    from models import SREAction
```

Required because the import path differs between local development (`server.app`) and Docker (`PYTHONPATH=/app`).

---

## Performance

- Single containers handle ~2,048 concurrent sessions via WebSocket
- Multi-container deployments use Envoy load balancing
- Benchmark: 256 sessions per CPU core (local Docker)
