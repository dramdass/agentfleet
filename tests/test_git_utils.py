"""Tests for git utility helpers."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentfleet import git_utils


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

