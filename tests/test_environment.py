"""Basic tests for SRE Incident Commander environment.

Validates that each task can be reset, stepped through optimally,
and produces correct scores.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.environment import SREIncidentEnvironment
from models import SREAction


def make_env():
    return SREIncidentEnvironment()


# ------------------------------------------------------------------
# Task 1: Easy — The Traffic Spike
# ------------------------------------------------------------------

def test_easy_optimal():
    env = make_env()
    obs = env.reset(task_id="easy", noise_level=0.0)
    assert not obs.done
    assert obs.task_id == "easy"
    assert len(obs.active_alerts) > 0

    # Step 1: Scale worker-node to 5
    # Queue dynamics first: growth=200, drain=2*100=200, net=0 -> queue=500
    # Then scale applies: replicas=5
    obs = env.step(SREAction(action_type="scale_service", service_name="worker-node", replicas=5))
    assert obs.reward == 0.2
    assert not obs.done

    # Step 2: Queue dynamics: growth=200, drain=5*100=500, net=-300 -> queue=200
    # Query logs is a neutral action to wait for drain
    obs = env.step(SREAction(action_type="query_logs", service_name="worker-node"))
    assert not obs.done

    # Step 3: Queue dynamics: growth=200, drain=500, net=-300 -> queue=0 -> auto-resolve
    obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    assert obs.done or env.state.completed
    score = env.state.current_score
    assert score == 1.0, f"Easy optimal score should be 1.0, got {score}"


def test_easy_wrong_action_penalizes():
    env = make_env()
    env.reset(task_id="easy")
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="worker-node", version="v1.3.0"))
    assert obs.reward < 0, "Wrong action should penalize"


# ------------------------------------------------------------------
# Task 2: Medium — The Poison Pill
# ------------------------------------------------------------------

def test_medium_optimal():
    env = make_env()
    obs = env.reset(task_id="medium", noise_level=0.0)
    assert not obs.done

    # Step 1: Query api-gateway logs
    obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    assert obs.reward > 0, "Querying api-gateway logs should reward"

    # Step 2: Rollback to v2.0.9
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="api-gateway", version="v2.0.9"))
    assert obs.done
    score = env.state.current_score
    assert score == 1.0, f"Medium optimal score should be 1.0, got {score}"


def test_medium_scaling_trap():
    env = make_env()
    env.reset(task_id="medium")
    obs = env.step(SREAction(action_type="scale_service", service_name="api-gateway", replicas=8))
    assert obs.reward == -0.5, "Scaling broken service should give -0.5"


def test_medium_non_primary_log_reward():
    env = make_env()
    env.reset(task_id="medium")
    obs = env.step(SREAction(action_type="query_logs", service_name="worker-node"))
    assert obs.reward == 0.05, f"Non-primary log query should give +0.05, got {obs.reward}"


# ------------------------------------------------------------------
# Task 3: Hard — The Cascading Lock
# ------------------------------------------------------------------

def test_hard_optimal():
    env = make_env()
    obs = env.reset(task_id="hard", noise_level=0.0)
    assert not obs.done

    # Diagnostic chain
    obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    assert obs.reward == 0.1

    obs = env.step(SREAction(action_type="query_logs", service_name="worker-node"))
    assert obs.reward == 0.1

    obs = env.step(SREAction(action_type="query_logs", service_name="database"))
    assert obs.reward == 0.1

    # Kill the lock
    obs = env.step(SREAction(action_type="kill_query", query_id="4287"))
    assert obs.reward == 0.4

    # Scale to recover
    obs = env.step(SREAction(action_type="scale_service", service_name="worker-node", replicas=6))
    assert obs.done
    score = env.state.current_score
    assert score == 1.0, f"Hard optimal score should be 1.0, got {score}"


def test_hard_wrong_pid_penalizes():
    env = make_env()
    env.reset(task_id="hard")
    obs = env.step(SREAction(action_type="kill_query", query_id="4290"))
    assert obs.reward < 0, "Killing wrong PID should penalize"


def test_hard_rollback_red_herring():
    env = make_env()
    env.reset(task_id="hard")
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="worker-node", version="v3.1.0"))
    assert obs.reward == -0.15, "Rollback red herring should give -0.15"


# ------------------------------------------------------------------
# Task 4: Memory Leak — The Silent OOM
# ------------------------------------------------------------------

def test_memory_leak_optimal():
    env = make_env()
    obs = env.reset(task_id="memory_leak", noise_level=0.0)
    assert not obs.done

    # Diagnose
    obs = env.step(SREAction(action_type="query_logs", service_name="payment-service"))
    assert obs.reward == 0.3

    # Mitigate
    obs = env.step(SREAction(action_type="restart_service", service_name="payment-service"))
    assert obs.reward == 0.1

    # Permanent fix
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="payment-service", version="v4.0.2"))
    assert obs.done
    assert obs.reward == 0.5
    score = env.state.current_score
    assert score == 1.0, f"Memory leak optimal score should be 1.0, got {score}"


def test_memory_leak_scaling_trap():
    env = make_env()
    env.reset(task_id="memory_leak")
    obs = env.step(SREAction(action_type="scale_service", service_name="payment-service", replicas=6))
    assert obs.reward == -0.15, "Scaling leaking service should give -0.15"


# ------------------------------------------------------------------
# Task 5: Cert Expiry — The Midnight Expiry
# ------------------------------------------------------------------

def test_cert_expiry_optimal():
    env = make_env()
    obs = env.reset(task_id="cert_expiry", noise_level=0.0)
    assert not obs.done

    # Investigate mesh proxy (most direct path)
    obs = env.step(SREAction(action_type="query_logs", service_name="service-mesh-proxy"))
    assert obs.reward == 0.2

    # Rotate certs
    obs = env.step(SREAction(action_type="rotate_certs"))
    assert obs.reward == 0.3

    # Restart 3 services
    obs = env.step(SREAction(action_type="restart_service", service_name="api-gateway"))
    assert obs.reward == 0.1

    obs = env.step(SREAction(action_type="restart_service", service_name="payment-service"))
    assert obs.reward == 0.1

    obs = env.step(SREAction(action_type="restart_service", service_name="worker-node"))
    assert obs.done
    score = env.state.current_score
    assert score > 0.7, f"Cert expiry optimal score should be >0.7, got {score}"


def test_cert_expiry_rollback_red_herring():
    env = make_env()
    env.reset(task_id="cert_expiry")
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="api-gateway", version="v4.9.0"))
    assert obs.reward == -0.15, "Rollback red herring should give -0.15"


def test_cert_expiry_any_rollback_is_red_herring():
    env = make_env()
    env.reset(task_id="cert_expiry")
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="worker-node", version="v3.0.0"))
    assert obs.reward == -0.15, "Any rollback should trigger red herring penalty"


# ------------------------------------------------------------------
# General: reset produces clean state
# ------------------------------------------------------------------

def test_reset_clears_state():
    env = make_env()
    env.reset(task_id="easy")
    env.step(SREAction(action_type="scale_service", service_name="worker-node", replicas=5))

    # Reset to a different task
    obs = env.reset(task_id="medium", noise_level=0.0)
    assert obs.task_id == "medium"
    assert obs.attempt_number == 0
    assert env.state.current_score == 0.0


def test_all_tasks_reset():
    """Every task can be reset without error."""
    env = make_env()
    for task_id in ["easy", "medium", "hard", "memory_leak", "cert_expiry", "perfect_storm"]:
        obs = env.reset(task_id=task_id, noise_level=0.0)
        assert not obs.done
        assert obs.task_id == task_id
        assert len(obs.active_alerts) > 0


def test_randomization_changes_pids():
    """Randomization should change PIDs in hard task."""
    env = make_env()
    env.reset(task_id="hard", seed=42, noise_level=1.0)
    pid1 = env._ts._random_pid_map.get("4287", "4287")
    env.reset(task_id="hard", seed=99, noise_level=1.0)
    pid2 = env._ts._random_pid_map.get("4287", "4287")
    assert pid1 != pid2, "Different seeds should randomize PIDs"


def test_perfect_storm_optimal():
    env = make_env()
    env.reset(task_id="perfect_storm", noise_level=0.0)

    obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    assert obs.reward == 0.1

    obs = env.step(SREAction(action_type="query_logs", service_name="database"))
    assert obs.reward == 0.1

    obs = env.step(SREAction(action_type="rollback_deployment", service_name="api-gateway", version="v5.9.2"))
    assert obs.reward == 0.3

    obs = env.step(SREAction(action_type="kill_query", query_id="5521"))
    assert obs.reward == 0.2

    obs = env.step(SREAction(action_type="scale_service", service_name="worker-node", replicas=4))
    assert obs.reward == 0.1

    score = env.state.current_score
    assert score >= 0.99, f"Perfect storm optimal score should be ~1.0, got {score}"


def test_perfect_storm_wrong_triage():
    """Killing DB leak before rolling back deploy should be penalized."""
    env = make_env()
    env.reset(task_id="perfect_storm", noise_level=0.0)
    env.step(SREAction(action_type="query_logs", service_name="database"))
    obs = env.step(SREAction(action_type="kill_query", query_id="5521"))
    assert obs.reward < 0, f"Wrong triage should be penalized, got reward={obs.reward}"


def test_score_normalized_0_to_1():
    """Scores should always be in [0.0, 1.0]."""
    env = make_env()
    for task_id in ["easy", "medium", "hard", "memory_leak", "cert_expiry", "perfect_storm"]:
        env.reset(task_id=task_id, noise_level=0.0)
        # Take several wrong actions
        for _ in range(3):
            env.step(SREAction(action_type="rotate_certs"))
        score = env.state.current_score
        assert 0.0 <= score <= 1.0, f"Task {task_id} score out of range: {score}"


# ------------------------------------------------------------------
# Parametrized: every action type on every task (42 combos)
# ------------------------------------------------------------------

import pytest

ALL_TASKS = ["easy", "medium", "hard", "memory_leak", "cert_expiry", "perfect_storm"]
ALL_ACTIONS = [
    ("query_logs", {"service_name": "nonexistent"}),
    ("scale_service", {"service_name": "nonexistent", "replicas": 5}),
    ("rollback_deployment", {"service_name": "nonexistent", "version": "v0.0.0"}),
    ("kill_query", {"query_id": "9999"}),
    ("restart_service", {"service_name": "nonexistent"}),
    ("rotate_certs", {}),
    ("resolve_incident", {}),
]


@pytest.mark.parametrize("task_id", ALL_TASKS)
@pytest.mark.parametrize("action_type,params", ALL_ACTIONS, ids=[a[0] for a in ALL_ACTIONS])
def test_all_actions_no_crash(task_id, action_type, params):
    """Every action type on every task must not crash and must return feedback."""
    env = make_env()
    env.reset(task_id=task_id, noise_level=0.0)
    obs = env.step(SREAction(action_type=action_type, reasoning="test", **params))
    assert obs.feedback, f"{task_id}/{action_type}: empty feedback"
    assert isinstance(obs.reward, (int, float)) or obs.reward is None


# ------------------------------------------------------------------
# Parametrized: score always in [0, 1] after wrong actions
# ------------------------------------------------------------------

@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_score_bounds_after_bad_actions(task_id):
    """Score must stay in [0.0, 1.0] even after many wrong actions."""
    env = make_env()
    env.reset(task_id=task_id, noise_level=0.0)
    for _ in range(8):
        env.step(SREAction(action_type="rotate_certs", reasoning="spam"))
    score = env.state.current_score
    assert 0.0 <= score <= 1.0, f"{task_id} score out of bounds: {score}"


# ------------------------------------------------------------------
# Max attempts auto-close
# ------------------------------------------------------------------

@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_max_attempts_auto_close(task_id):
    """Episode must auto-close when max_attempts reached."""
    env = make_env()
    obs = env.reset(task_id=task_id, noise_level=0.0)
    max_steps = obs.max_attempts
    for _ in range(max_steps + 5):
        obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway", reasoning="stall"))
        if obs.done:
            break
    assert obs.done, f"{task_id}: not done after max_attempts={max_steps}"


# ------------------------------------------------------------------
# Step after done returns gracefully
# ------------------------------------------------------------------

def test_step_after_done():
    """Stepping after episode is done should not crash."""
    env = make_env()
    env.reset(task_id="medium", noise_level=0.0)
    env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    env.step(SREAction(action_type="rollback_deployment", service_name="api-gateway", version="v2.0.9"))
    # Episode is done now
    obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway", reasoning="after done"))
    assert obs.done
    assert "closed" in obs.feedback.lower() or "reset" in obs.feedback.lower()


# ------------------------------------------------------------------
# Step without reset returns error
# ------------------------------------------------------------------

def test_step_without_reset():
    """Stepping without calling reset should return done=True with error feedback."""
    env = make_env()
    obs = env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    assert obs.done
    assert "reset" in obs.feedback.lower() or "initialised" in obs.feedback.lower()


# ------------------------------------------------------------------
# Randomization: same seed = same result
# ------------------------------------------------------------------

def test_same_seed_deterministic():
    """Same seed should produce identical episodes."""
    env = make_env()
    obs1 = env.reset(task_id="hard", seed=42, noise_level=1.0)
    pid1 = env._ts._random_pid_map.get("4287", "4287")
    metrics1 = dict(obs1.system_metrics)

    obs2 = env.reset(task_id="hard", seed=42, noise_level=1.0)
    pid2 = env._ts._random_pid_map.get("4287", "4287")
    metrics2 = dict(obs2.system_metrics)

    assert pid1 == pid2, "Same seed should produce same PID"
    assert metrics1 == metrics2, "Same seed should produce same metrics"


# ------------------------------------------------------------------
# Randomization: noise_level=0 means deterministic
# ------------------------------------------------------------------

def test_noise_zero_deterministic():
    """noise_level=0 should produce identical state regardless of seed."""
    env = make_env()
    obs1 = env.reset(task_id="hard", seed=1, noise_level=0.0)
    obs2 = env.reset(task_id="hard", seed=9999, noise_level=0.0)
    assert obs1.system_metrics == obs2.system_metrics


# ------------------------------------------------------------------
# Perfect storm: randomization changes PID
# ------------------------------------------------------------------

def test_perfect_storm_randomized_pid():
    """Perfect storm PID should change with different seeds."""
    env = make_env()
    env.reset(task_id="perfect_storm", seed=10, noise_level=1.0)
    pid1 = env._ts._random_pid_map.get("5521", "5521")
    env.reset(task_id="perfect_storm", seed=99, noise_level=1.0)
    pid2 = env._ts._random_pid_map.get("5521", "5521")
    assert pid1 != pid2, "Different seeds should randomize perfect_storm PID"


# ------------------------------------------------------------------
# Timeline recording
# ------------------------------------------------------------------

@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_timeline_recorded(task_id):
    """Every step should produce a timeline entry in state."""
    env = make_env()
    env.reset(task_id=task_id, noise_level=0.0)
    env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    state = env.state
    assert len(state.timeline) == 2, f"{task_id}: expected 2 timeline entries, got {len(state.timeline)}"
    assert state.timeline[0]["step"] == 1
    assert state.timeline[1]["step"] == 2
    assert state.timeline[0]["action"] == "query_logs"


# ------------------------------------------------------------------
# State endpoint correctness
# ------------------------------------------------------------------

@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_state_fields(task_id):
    """State should have correct fields after reset and step."""
    env = make_env()
    env.reset(task_id=task_id, noise_level=0.0)
    state = env.state
    assert state.task_id == task_id
    assert state.step_count == 0
    assert state.current_score == 0.0
    assert state.completed is False
    assert state.actions_taken == []

    env.step(SREAction(action_type="query_logs", service_name="api-gateway"))
    state = env.state
    assert state.step_count == 1
    assert "query_logs" in state.actions_taken


# ------------------------------------------------------------------
# Observation fields on reset
# ------------------------------------------------------------------

@pytest.mark.parametrize("task_id", ALL_TASKS)
def test_observation_fields_on_reset(task_id):
    """Reset observation must have all required fields populated."""
    env = make_env()
    obs = env.reset(task_id=task_id, noise_level=0.0)
    assert obs.task_id == task_id
    assert obs.difficulty != ""
    assert obs.attempt_number == 0
    assert obs.max_attempts > 0
    assert obs.uptime_percentage == 100.0
    assert obs.cloud_cost_usd == 0.0
    assert len(obs.active_alerts) > 0
    assert len(obs.services) > 0
    assert len(obs.system_metrics) > 0
    assert obs.feedback != ""
    assert obs.hint != ""
    assert obs.current_deployment_version != ""


# ------------------------------------------------------------------
# Easy: resolve with full queue fails
# ------------------------------------------------------------------

def test_easy_resolve_with_full_queue():
    """Cannot resolve easy task while queue is still full."""
    env = make_env()
    env.reset(task_id="easy", noise_level=0.0)
    obs = env.step(SREAction(action_type="resolve_incident"))
    assert obs.reward < 0
    assert not obs.done


# ------------------------------------------------------------------
# Medium: wrong rollback version
# ------------------------------------------------------------------

def test_medium_wrong_version():
    """Rolling back to wrong version should penalize."""
    env = make_env()
    env.reset(task_id="medium", noise_level=0.0)
    obs = env.step(SREAction(action_type="rollback_deployment", service_name="api-gateway", version="v1.0.0"))
    assert obs.reward == -0.1


# ------------------------------------------------------------------
# Hard: scale before kill penalized
# ------------------------------------------------------------------

def test_hard_scale_before_kill():
    """Scaling worker-node before killing the lock should penalize."""
    env = make_env()
    env.reset(task_id="hard", noise_level=0.0)
    obs = env.step(SREAction(action_type="scale_service", service_name="worker-node", replicas=8))
    assert obs.reward == -0.1


# ------------------------------------------------------------------
# Memory leak: restart is temporary
# ------------------------------------------------------------------

def test_memory_leak_restart_then_resolve_fails():
    """Restarting without rollback should not allow resolution."""
    env = make_env()
    env.reset(task_id="memory_leak", noise_level=0.0)
    env.step(SREAction(action_type="restart_service", service_name="payment-service"))
    obs = env.step(SREAction(action_type="resolve_incident"))
    assert obs.reward < 0
    assert not obs.done


# ------------------------------------------------------------------
# Cert expiry: restart before rotate fails
# ------------------------------------------------------------------

def test_cert_expiry_restart_before_rotate():
    """Restarting services before rotating certs should penalize."""
    env = make_env()
    env.reset(task_id="cert_expiry", noise_level=0.0)
    obs = env.step(SREAction(action_type="restart_service", service_name="api-gateway"))
    assert obs.reward == -0.1


# ------------------------------------------------------------------
# Cert expiry: blind rotate works but penalized
# ------------------------------------------------------------------

def test_cert_expiry_blind_rotate():
    """Rotating certs without diagnosis should work but with small penalty."""
    env = make_env()
    env.reset(task_id="cert_expiry", noise_level=0.0)
    obs = env.step(SREAction(action_type="rotate_certs"))
    assert obs.reward == -0.05
    assert "blindly" in obs.feedback.lower()


# ------------------------------------------------------------------
# Invalid task_id falls back to easy
# ------------------------------------------------------------------

def test_invalid_task_falls_back():
    """Invalid task_id should fall back to easy."""
    env = make_env()
    obs = env.reset(task_id="nonexistent_task", noise_level=0.0)
    assert obs.task_id == "easy"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests")
    sys.exit(1 if failed else 0)
