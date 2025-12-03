"""Command-line interface for AgentFleet."""

import argparse
import asyncio
import sys
from pathlib import Path

from agentfleet.planner import generate_plan
from agentfleet.tournament import run_tournament
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

    try:
        # Phase 1: Generate evaluation plan
        with show_spinner("Generating evaluation plan...") as progress:
            task_id = progress.add_task("Planning...", total=None)
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
            task_id = progress.add_task("Tournament in progress...", total=None)
            tournament_result = await run_tournament(
                task=args.task,
                approaches=args.approaches,
                plan=plan,
                max_iterations=args.max_iter,
                mode=mode,
                work_base_dir=args.work_dir,
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


if __name__ == "__main__":
    sys.exit(main())
