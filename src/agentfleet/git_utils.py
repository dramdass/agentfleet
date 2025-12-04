"""Utilities for preparing git repositories before running tournaments."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

from agentfleet.models import AgentResult, TournamentResult


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


def format_agent_branch(approach: str) -> str:
    """Create a deterministic branch name for an approach."""
    sanitized = approach.strip().lower()
    sanitized = re.sub(r"[^a-z0-9]+", "-", sanitized)
    sanitized = sanitized.strip("-")
    if not sanitized:
        sanitized = "approach"
    return f"agent/{sanitized}"


def build_pr_body(tournament: TournamentResult) -> str:
    """Build a Markdown pull request body summarizing results."""
    plan = tournament.plan
    winner = tournament.winner

    lines: list[str] = []
    lines.append("# AgentFleet Tournament Summary\n")
    lines.append(f"**Task:** {plan.resolved_task}\n")

    if winner:
        status = "✅ PASS" if winner.success else "⚠️ Needs fixes"
        lines.append("## Winner\n")
        lines.append(
            f"- Approach: **{winner.approach}** ({status}, {winner.score:.1f}/100)\n"
        )
        lines.append(f"- Iterations: {winner.iteration_count}")
        lines.append(f"- Decisions recorded: {winner.decision_count}")
        if winner.metrics:
            metric_parts = ", ".join(
                f"{k}: {v}" for k, v in winner.metrics.items()
            )
            lines.append(f"- Metrics: {metric_parts}")
        if winner.work_dir:
            lines.append(f"- Worktree path: `{winner.work_dir}`")
        if winner.branch_name:
            lines.append(f"- Branch: `{winner.branch_name}`")
        lines.append("")

    lines.append("## Tournament Results\n")
    lines.append(
        "| Approach | Status | Score | Iterations | Decisions | Notes |\n"
        "| --- | --- | --- | --- | --- | --- |"
    )
    for result in tournament.results:
        status = "✅ PASS" if result.success else "❌ FAIL"
        notes = summarize_result_notes(result)
        lines.append(
            f"| {result.approach} | {status} | {result.score:.1f} | "
            f"{result.iteration_count} | {result.decision_count} | {notes} |"
        )
    lines.append("")

    if winner and winner.decision_trail:
        lines.append("## Decision Highlights\n")
        for idx, decision in enumerate(winner.decision_trail[:5], 1):
            mode = "BLOCKING" if decision.blocking else "Speculative"
            lines.append(
                f"{idx}. **{decision.question}** ({mode})\n"
                f"   - Options: {', '.join(decision.options)}\n"
                f"   - Chosen: {decision.chosen}\n"
                f"   - Reasoning: {decision.reasoning}\n"
            )
        if len(winner.decision_trail) > 5:
            lines.append(
                f"...and {len(winner.decision_trail) - 5} additional decisions recorded.\n"
            )

    lines.append("## Next Steps\n")
    lines.append(
        dedent(
            """\
            1. Review the winning branch diff.
            2. Run your own test suite or QA checks.
            3. Edit as needed.
            4. Merge into the base branch once satisfied.
            """
        )
    )

    return "\n".join(lines).strip() + "\n"


def summarize_result_notes(result: AgentResult) -> str:
    """Summarize key details for an agent result."""
    if result.success:
        return "All evaluation tests passed"
    if result.error:
        return result.error
    final_iteration = result.get_final_iteration()
    if final_iteration and final_iteration.error_messages:
        return final_iteration.error_messages[0]
    return "Tests failed; see logs"


def write_pr_body_file(work_base_dir: Path, branch_name: str, body: str) -> Path:
    """Persist the PR body so users can edit or reuse it."""
    safe_branch = branch_name.replace("/", "_")
    pr_dir = (work_base_dir or Path.cwd()).expanduser().resolve() / "agentfleet_pr"
    pr_dir.mkdir(parents=True, exist_ok=True)
    body_path = pr_dir / f"{safe_branch}.md"
    body_path.write_text(body)
    return body_path


def snapshot_worktree(worktree_path: Path, commit_message: str) -> bool:
    """Stage and commit any pending changes in a worktree.

    Returns:
        True if a commit was created, False if there were no changes.
    """
    worktree = worktree_path.expanduser().resolve()

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise ValueError("git executable not found. Cannot inspect worktree.") from None
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        raise ValueError(f"git status failed: {stderr}") from exc

    if not status.stdout.strip():
        return False

    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        raise ValueError(f"git commit failed: {stderr}") from exc

    return True


def push_branch(repo_path: Path, branch_name: str) -> tuple[bool, str | None]:
    """Push the branch to origin."""
    try:
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True, None
    except FileNotFoundError:
        return False, "git executable not found. Install git to push branches."
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        return False, stderr or "git push failed."


def create_pull_request(
    repo_path: Path,
    branch_name: str,
    base_branch: str,
    title: str,
    body_file: Path,
) -> tuple[str, str | None]:
    """Create a pull request via gh, falling back to manual instructions.

    Returns:
        Tuple(status, message_or_url). Status may be 'created', 'manual', or 'error'.
    """
    pushed, push_msg = push_branch(repo_path, branch_name)
    if not pushed:
        return "error", f"Failed to push branch '{branch_name}': {push_msg}"

    gh_path = shutil.which("gh")
    if gh_path:
        try:
            result = subprocess.run(
                [
                    gh_path,
                    "pr",
                    "create",
                    "--base",
                    base_branch,
                    "--head",
                    branch_name,
                    "--title",
                    title,
                    "--body-file",
                    str(body_file),
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            stdout = result.stdout.strip()
            pr_url = stdout.splitlines()[-1] if stdout else "PR created"
            return "created", pr_url
        except subprocess.CalledProcessError as exc:
            error_msg = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
            manual = dedent(
                f"""\
                Auto PR creation failed ({error_msg}).
                You can create it manually with:
                  cd {repo_path}
                  gh pr create --base {base_branch} --head {branch_name} --title "{title}" --body-file "{body_file}"
                """
            )
            return "manual", manual

    manual_msg = dedent(
        f"""\
        gh CLI not found. Branch has been pushed to origin.
        Create the PR manually:
          cd {repo_path}
          gh pr create --base {base_branch} --head {branch_name} --title "{title}" --body-file "{body_file}"
        """
    )
    return "manual", manual_msg.strip()

