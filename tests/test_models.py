"""Unit tests for AgentFleet data models."""

import pytest
import time

from agentfleet.models import (
    Decision,
    Iteration,
    Plan,
    AgentResult,
    TournamentResult,
)


def test_decision_creation():
    """Test Decision dataclass creation."""
    decision = Decision(
        question="Should we use Redis?",
        options=["yes", "no"],
        chosen="no",
        reasoning="No persistence requirement specified",
        blocking=False,
    )

    assert decision.question == "Should we use Redis?"
    assert decision.chosen == "no"
    assert not decision.blocking
    assert decision.timestamp > 0


def test_iteration_creation():
    """Test Iteration dataclass creation."""
    iteration = Iteration(
        attempt=1,
        tests_passed=4,
        tests_failed=1,
        decisions_made=[],
        error_messages=["Test failed: boundary case"],
    )

    assert iteration.attempt == 1
    assert iteration.total_tests == 5
    assert not iteration.success


def test_iteration_success():
    """Test Iteration success property."""
    success_iter = Iteration(
        attempt=2,
        tests_passed=5,
        tests_failed=0,
    )

    assert success_iter.success
    assert success_iter.total_tests == 5


def test_plan_creation():
    """Test Plan dataclass creation and validation."""
    plan = Plan(
        resolved_task="Implement rate limiter",
        interface_contract="class RateLimiter:\n    def allow_request(self, user_id: str) -> bool:",
        tests=[
            {"name": "test_basic", "category": "correctness"},
            {"name": "test_edge", "category": "edge_cases"},
        ],
        metrics=["correctness_score", "simplicity_score"],
        weights={"correctness": 70.0, "simplicity": 30.0},
        eval_script="# eval code here",
    )

    assert plan.test_count == 2
    assert plan.get_category_weight("correctness") == 70.0


def test_plan_invalid_weights():
    """Test Plan raises error for invalid weights."""
    with pytest.raises(ValueError, match="must sum to 100"):
        Plan(
            resolved_task="Task",
            interface_contract="code",
            tests=[],
            metrics=[],
            weights={"correctness": 50.0, "simplicity": 30.0},  # Only sums to 80
            eval_script="code",
        )


def test_agent_result_creation():
    """Test AgentResult dataclass creation."""
    result = AgentResult(
        approach="Token bucket",
        success=True,
        iterations=[
            Iteration(attempt=1, tests_passed=3, tests_failed=2),
            Iteration(attempt=2, tests_passed=5, tests_failed=0),
        ],
        decision_trail=[
            Decision(
                question="Use dict or deque?",
                options=["dict", "deque"],
                chosen="dict",
                reasoning="Simpler",
            )
        ],
        metrics={"correctness_score": 1.0, "simplicity_score": 0.9},
        final_code="class RateLimiter: pass",
        work_dir="/tmp/work",
    )

    assert result.iteration_count == 2
    assert result.decision_count == 1
    assert result.converged


def test_agent_result_failed():
    """Test AgentResult for failed agent."""
    result = AgentResult(
        approach="Broken approach",
        success=False,
        iterations=[],
        decision_trail=[],
        metrics={},
        final_code="",
        work_dir="/tmp/work",
        error="Max iterations reached",
    )

    assert not result.converged
    assert result.error is not None


def test_tournament_result_sorting():
    """Test TournamentResult sorts by score."""
    results = [
        AgentResult(
            approach="Approach A",
            success=True,
            iterations=[],
            decision_trail=[],
            metrics={},
            final_code="",
            work_dir="/tmp/a",
            score=75.0,
        ),
        AgentResult(
            approach="Approach B",
            success=True,
            iterations=[],
            decision_trail=[],
            metrics={},
            final_code="",
            work_dir="/tmp/b",
            score=95.0,
        ),
        AgentResult(
            approach="Approach C",
            success=False,
            iterations=[],
            decision_trail=[],
            metrics={},
            final_code="",
            work_dir="/tmp/c",
            score=50.0,
        ),
    ]

    plan = Plan(
        resolved_task="Task",
        interface_contract="code",
        tests=[],
        metrics=[],
        weights={"correctness": 100.0},
        eval_script="code",
    )

    tournament = TournamentResult(results=results, plan=plan)

    # Should be sorted by score descending
    assert tournament.winner.approach == "Approach B"
    assert tournament.results[0].score == 95.0
    assert tournament.results[1].score == 75.0
    assert tournament.results[2].score == 50.0


def test_tournament_result_get_result():
    """Test TournamentResult.get_result method."""
    results = [
        AgentResult(
            approach="Token bucket",
            success=True,
            iterations=[],
            decision_trail=[],
            metrics={},
            final_code="",
            work_dir="/tmp/a",
            score=80.0,
        ),
    ]

    plan = Plan(
        resolved_task="Task",
        interface_contract="code",
        tests=[],
        metrics=[],
        weights={"correctness": 100.0},
        eval_script="code",
    )

    tournament = TournamentResult(results=results, plan=plan)

    result = tournament.get_result("Token bucket")
    assert result is not None
    assert result.approach == "Token bucket"

    not_found = tournament.get_result("Nonexistent")
    assert not_found is None


def test_tournament_result_top_n():
    """Test TournamentResult.get_top_n method."""
    results = [
        AgentResult(
            approach=f"Approach {i}",
            success=True,
            iterations=[],
            decision_trail=[],
            metrics={},
            final_code="",
            work_dir=f"/tmp/{i}",
            score=float(i * 10),
        )
        for i in range(5)
    ]

    plan = Plan(
        resolved_task="Task",
        interface_contract="code",
        tests=[],
        metrics=[],
        weights={"correctness": 100.0},
        eval_script="code",
    )

    tournament = TournamentResult(results=results, plan=plan)
    top_3 = tournament.get_top_n(3)

    assert len(top_3) == 3
    assert top_3[0].score >= top_3[1].score >= top_3[2].score
