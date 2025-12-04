"""Tests for git utility helpers."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentfleet import git_utils
from agentfleet.models import Plan, AgentResult, Iteration, TournamentResult


def test_resolve_repo_accepts_existing_path(monkeypatch, tmp_path):
    repo_dir = tmp_path / "existing"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()

    def fake_run(cmd, cwd=None, capture_output=False, text=False, check=False):
        assert cmd[:2] == ["git", "rev-parse"]
        assert cwd == repo_dir
        return SimpleNamespace(returncode=0, stdout="true", stderr="")

    monkeypatch.setattr(git_utils.subprocess, "run", fake_run)

    resolved = git_utils.resolve_repo(str(repo_dir), tmp_path)
    assert resolved == repo_dir.resolve()


def test_resolve_repo_clones_remote_when_missing(monkeypatch, tmp_path):
    work_dir = tmp_path / "work"
    remote = "https://github.com/example/awesome-repo.git"
    clone_path = work_dir / "repos" / "github.com-example-awesome-repo"

    def fake_run(cmd, cwd=None, capture_output=False, text=False, check=False):
        if cmd[:2] == ["git", "clone"]:
            destination = Path(cmd[-1])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / ".git").mkdir()
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="true", stderr="")
        raise AssertionError(f"Unexpected git command: {cmd}")

    monkeypatch.setattr(git_utils.subprocess, "run", fake_run)

    resolved = git_utils.resolve_repo(remote, work_dir)
    assert resolved == clone_path.resolve()


def test_resolve_repo_rejects_invalid_string(tmp_path):
    with pytest.raises(ValueError, match="existing directory or a Git URL"):
        git_utils.resolve_repo("not-a-repo", tmp_path)


def test_format_agent_branch_sanitizes_names():
    assert git_utils.format_agent_branch("Sliding Window!") == "agent/sliding-window"
    assert git_utils.format_agent_branch("  ") == "agent/approach"


def test_build_pr_body_includes_results():
    plan = Plan(
        resolved_task="Add rate limiting to app.py",
        interface_contract="class RateLimiter:\n    ...",
        tests=[],
        metrics=["correctness_score"],
        weights={"correctness": 100.0},
        eval_script="# eval",
    )

    iteration = Iteration(
        attempt=1,
        tests_passed=5,
        tests_failed=0,
    )

    result = AgentResult(
        approach="Sliding window",
        success=True,
        iterations=[iteration],
        decision_trail=[],
        metrics={"correctness_score": 1.0},
        final_code="print('hi')",
        work_dir="/tmp/agent/sliding-window",
        branch_name="agent/sliding-window",
    )

    tournament = TournamentResult(results=[result], plan=plan)

    body = git_utils.build_pr_body(tournament)
    assert "Sliding window" in body
    assert "agent/sliding-window" in body


