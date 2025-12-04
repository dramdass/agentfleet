"""Command-line interface for AgentFleet."""

import argparse
import asyncio
import sys
from pathlib import Path

from agentfleet.planner import generate_plan
from agentfleet.tournament import run_tournament
from agentfleet.git_utils import (
    resolve_repo,
    build_pr_body,
    create_pull_request,
    format_agent_branch,
    write_pr_body_file,
    snapshot_worktree,
)
from agentfleet.display import (
    print_plan,
    print_results,
    print_decisions,
    print_code,
    save_winner,
    prompt_confirmation,
    show_menu,
    print_error,
    print_success,
    print_warning,
    show_spinner,
    console,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="AgentFleet: Multi-agent tournament system for comparing LLM implementation approaches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic tournament
  agentfleet "Implement rate limiter" "Token bucket" "Sliding window" "Fixed window"

  # Interactive mode (pause at decisions)
  agentfleet "Implement rate limiter" "Token bucket" "Sliding window" --interactive

  # Speculative mode (auto-run, no prompts)
  agentfleet "Implement rate limiter" "Token bucket" "Sliding window" --yes

  # Custom iteration limit
  agentfleet "Implement rate limiter" "Token bucket" "Sliding window" --max-iter 15
        """,
    )

    parser.add_argument(
        "task",
        help="Programming task description (use quotes for multi-word tasks)",
    )

    parser.add_argument(
        "approaches",
        nargs="+",
        help="Approaches to compare (2-5 approaches, e.g., 'Token bucket' 'Sliding window')",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept defaults and run in speculative mode (no confirmations)",
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode (pause at blocking decisions)",
    )

    parser.add_argument(
        "--max-iter",
        type=int,
        default=10,
        help="Maximum iterations per agent (default: 10)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress during execution",
    )

    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path.cwd() / "work",
        help="Base directory for agent workspaces (default: ./work)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Save winner's code to this file (default: winner.py)",
    )

    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Absolute path or GitHub URL for the target repository (agents create worktrees with branches like agent/token-bucket)",
    )

    parser.add_argument(
        "--base-branch",
        type=str,
        default="main",
        help="Base branch for pull requests (default: main)",
    )

    parser.add_argument(
        "--skip-pr",
        action="store_true",
        help="Skip automatic pull request creation for the winning branch",
    )

    return parser.parse_args()


async def main_async() -> int:
    """Main async entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    # Validate arguments
    if len(args.approaches) < 2:
        print_error("Tournament requires at least 2 approaches")
        return 1

    if len(args.approaches) > 5:
        print_error("Tournament supports at most 5 approaches")
        return 1

    # Print header
    console.print("\n[bold cyan]AgentFleet Tournament System[/bold cyan]\n")
    console.print(f"Task: [bold]{args.task}[/bold]")
    console.print(f"Approaches: {', '.join(args.approaches)}\n")

    repo_arg = args.repo.strip()
    if not repo_arg:
        print_error("--repo must be a non-empty absolute path or GitHub URL")
        return 1

    try:
        repo_path = resolve_repo(repo_arg, args.work_dir)
    except ValueError as exc:
        print_error(str(exc))
        return 1

    try:
        # Phase 1: Generate evaluation plan
        with show_spinner("Generating evaluation plan...") as progress:
            progress.add_task("Planning...", total=None)
            plan = await generate_plan(args.task, args.approaches)
            progress.stop()

        print_success("Evaluation plan generated")
        print_plan(plan)

        # Confirm plan (unless --yes)
        if not args.yes:
            if not prompt_confirmation("Proceed with this plan?"):
                console.print("[yellow]Tournament cancelled[/yellow]")
                return 0

        # Phase 2: Run tournament
        mode = "interactive" if args.interactive else "speculative"
        console.print(f"\n[bold cyan]Starting tournament ({mode} mode)...[/bold cyan]\n")

        with show_spinner("Running agents...") as progress:
            progress.add_task("Tournament in progress...", total=None)
            tournament_result = await run_tournament(
                task=args.task,
                approaches=args.approaches,
                plan=plan,
                max_iterations=args.max_iter,
                mode=mode,
                work_base_dir=args.work_dir,
                source_repo=repo_path,
            )
            progress.stop()

        print_success("Tournament complete")

        # Phase 3: Display results
        print_results(tournament_result)

        # Phase 4: Interactive menu
        if not args.yes:
            while True:
                console.print("\n[bold]What would you like to do?[/bold]")
                options = [
                    "View solution code",
                    "View decision trail",
                    "Save winner's code",
                    "Exit",
                ]
                choice = show_menu(options)

                if choice == 0:  # View code
                    console.print("\n[bold]Select approach:[/bold]")
                    approach_idx = show_menu(tournament_result.approaches)
                    approach = tournament_result.approaches[approach_idx]
                    print_code(tournament_result, approach)

                elif choice == 1:  # View decisions
                    console.print("\n[bold]Select approach:[/bold]")
                    approach_idx = show_menu(tournament_result.approaches)
                    approach = tournament_result.approaches[approach_idx]
                    print_decisions(tournament_result, approach)

                elif choice == 2:  # Save winner
                    save_winner(tournament_result, args.output)

                elif choice == 3:  # Exit
                    break

        # Auto-save if --output specified
        elif args.output:
            save_winner(tournament_result, args.output)

        pr_outcome = None
        if not args.skip_pr:
            pr_outcome = _maybe_create_pull_request(
                tournament_result=tournament_result,
                repo_path=repo_path,
                base_branch=args.base_branch,
                work_dir=args.work_dir,
            )

        if pr_outcome:
            status, info = pr_outcome
            if status == "created":
                print_success(f"Pull request created: {info}")
            elif status == "manual":
                print_warning(info)
            else:
                print_error(info)

        console.print("\n[bold green]Done![/bold green]\n")
        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 130
    except Exception as e:
        print_error(str(e))
        if args.verbose:
            import traceback

            console.print("\n[dim]" + traceback.format_exc() + "[/dim]")
        return 1


def main() -> int:
    """Main entry point (synchronous wrapper).

    Returns:
        Exit code
    """
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 130


def _maybe_create_pull_request(
    tournament_result,
    repo_path: Path,
    base_branch: str,
    work_dir: Path,
) -> tuple[str, str | None] | None:
    """Create a PR for the winning branch, if possible."""
    winner = tournament_result.winner
    if not winner:
        return None

    branch_name = winner.branch_name or format_agent_branch(winner.approach)
    if not branch_name:
        return None

    worktree_path = Path(winner.work_dir).expanduser()
    commit_note = "pass" if winner.success else "draft"
    commit_message = f"AgentFleet: {winner.approach} ({commit_note})"

    try:
        changed = snapshot_worktree(worktree_path, commit_message)
    except ValueError as exc:
        return "error", f"Failed to prepare branch '{branch_name}': {exc}"

    if not changed:
        return (
            "manual",
            "Winning branch has no changes to commit. "
            "Inspect the worktree and commit modifications before opening a PR.",
        )

    pr_body = build_pr_body(tournament_result)
    body_file = write_pr_body_file(work_dir, branch_name, pr_body)
    title = _build_pr_title(winner.approach, tournament_result.plan.resolved_task)

    return create_pull_request(
        repo_path=repo_path,
        branch_name=branch_name,
        base_branch=base_branch,
        title=title,
        body_file=body_file,
    )


def _build_pr_title(approach: str, resolved_task: str) -> str:
    """Generate a concise PR title."""
    task = " ".join(resolved_task.split())
    if len(task) > 80:
        task = task[:77] + "..."
    return f"[AgentFleet] {approach} – {task}"


if __name__ == "__main__":
    sys.exit(main())
