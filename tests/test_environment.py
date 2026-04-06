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
    for task_id in ["easy", "medium", "hard", "memory_leak", "cert_expiry"]:
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
