"""Utilities for preparing git repositories before running tournaments."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def resolve_repo(repo_arg: str, work_base_dir: Path | None) -> Path:
    """Resolve a repo argument into an absolute git repository path.

    Args:
        repo_arg: Absolute path or Git URL pointing to the target repository.
        work_base_dir: Base directory (usually --work-dir) used for caching clones.

    Returns:
        Absolute Path to a valid git repository.

    Raises:
        ValueError: If the repo cannot be resolved or validated.
    """
    if not repo_arg:
        raise ValueError("Repository argument cannot be empty.")

    repo_arg = repo_arg.strip()
    base_dir = (work_base_dir or (Path.cwd() / "work")).expanduser().resolve()
    if base_dir.exists() and not base_dir.is_dir():
        raise ValueError(f"--work-dir must be a directory, got file: {base_dir}")
    base_dir.mkdir(parents=True, exist_ok=True)

    candidate_path = Path(repo_arg).expanduser()
    if candidate_path.exists():
        repo_path = candidate_path.resolve()
        _ensure_git_repo(repo_path)
        return repo_path

    if not _looks_like_git_url(repo_arg):
        raise ValueError(
            "Repository must be an existing directory or a Git URL "
            "(e.g., https://github.com/org/project.git)."
        )

    cache_root = base_dir / "repos"
    cache_root.mkdir(parents=True, exist_ok=True)

    repo_slug = _slugify_remote(repo_arg)
    target_path = cache_root / repo_slug

    if target_path.exists():
        _ensure_git_repo(target_path)
        return target_path

    _clone_repo(repo_arg, target_path)
    _ensure_git_repo(target_path)
    return target_path


def _clone_repo(remote: str, destination: Path) -> None:
    """Clone a remote repository to a local destination."""
    try:
        subprocess.run(
            ["git", "clone", remote, str(destination)],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise ValueError("git executable not found in PATH. Cannot clone repository.") from None
    except subprocess.CalledProcessError as exc:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        raise ValueError(f"Failed to clone repository '{remote}': {stderr}") from exc


def _ensure_git_repo(path: Path) -> None:
    """Ensure the provided path is a git work tree."""
    if not path.exists():
        raise ValueError(f"Repository path does not exist: {path}")

    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise ValueError("git executable not found in PATH. Cannot inspect repository.") from None
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        raise ValueError(f"Directory is not a git repository: {path}\n{stderr}") from exc


def _looks_like_git_url(value: str) -> bool:
    """Heuristically determine whether the string looks like a git URL."""
    lowered = value.lower()
    return lowered.startswith(("http://", "https://", "git@")) or lowered.endswith(".git")


def _slugify_remote(remote: str) -> str:
    """Create a deterministic folder name for a remote repository."""
    cleaned = remote.strip().rstrip("/")
    cleaned = cleaned.replace(":", "/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]

    cleaned = cleaned.split("://", 1)[-1]
    tokens = [token for token in cleaned.split("/") if token]
    slug_raw = "-".join(tokens[-3:]) if tokens else "repo"
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", slug_raw)
    return slug.lower()

