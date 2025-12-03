"""Terminal display functions for AgentFleet."""

from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from agentfleet.models import Plan, TournamentResult, AgentResult, Decision
from agentfleet.tournament import get_medal, format_score


console = Console()


def print_plan(plan: Plan) -> None:
    """Display evaluation plan before execution.

    Args:
        plan: The evaluation plan to display
    """
    console.print("\n" + "=" * 80)
    console.print("[bold cyan]EVALUATION PLAN[/bold cyan]", justify="center")
    console.print("=" * 80 + "\n")

    # Resolved task
    console.print("[bold]Resolved Task:[/bold]")
    console.print(plan.resolved_task)
    console.print()

    # Interface contract
    console.print("[bold]Interface Contract:[/bold]")
    syntax = Syntax(plan.interface_contract, "python", theme="monokai", line_numbers=False)
    console.print(syntax)
    console.print()

    # Tests
    console.print("[bold]Tests:[/bold]")
    for test in plan.tests:
        category = test.get("category", "unknown")
        name = test.get("name", "unnamed")
        desc = test.get("description", "")
        console.print(f"  • {name} ({category})")
        if desc:
            console.print(f"    {desc}")
    console.print()

    # Metrics
    console.print("[bold]Metrics:[/bold]")
    for metric in plan.metrics:
        console.print(f"  • {metric}")
    console.print()

    # Scoring weights
    console.print("[bold]Scoring Weights:[/bold]")
    for category, weight in plan.weights.items():
        console.print(f"  • {category}: {weight}%")
    console.print()


def print_results(tournament: TournamentResult) -> None:
    """Display final tournament results with rankings.

    Args:
        tournament: The tournament result to display
    """
    console.print("\n" + "=" * 80)
    console.print("[bold cyan]TOURNAMENT RESULTS[/bold cyan]", justify="center")
    console.print("=" * 80 + "\n")

    # Create results table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", justify="center", style="cyan", width=6)
    table.add_column("Approach", style="white", width=20)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Score", justify="right", style="green", width=10)
    table.add_column("Iterations", justify="center", width=10)
    table.add_column("Decisions", justify="center", width=10)

    for i, result in enumerate(tournament.results, 1):
        medal = get_medal(i)
        status = "✅ PASS" if result.success else "❌ FAIL"
        score_str = format_score(result.score)
        iterations = str(result.iteration_count)
        decisions = str(result.decision_count)

        # Highlight winner
        style = "bold yellow" if i == 1 else ""

        table.add_row(
            medal,
            result.approach,
            status,
            score_str,
            iterations,
            decisions,
            style=style,
        )

    console.print(table)
    console.print()

    # Winner details
    if tournament.winner:
        winner = tournament.winner
        panel_content = f"""[bold]{winner.approach}[/bold] wins with [green]{format_score(winner.score)}[/green]

Status: {'✅ All tests passed' if winner.success else '❌ Some tests failed'}
Iterations: {winner.iteration_count}
Decisions: {winner.decision_count} interpretive choices made

Metrics:
"""
        for key, value in winner.metrics.items():
            panel_content += f"  • {key}: {value}\n"

        console.print(
            Panel(panel_content, title="🏆 Winner", border_style="gold1", expand=False)
        )
        console.print()


def print_decisions(tournament: TournamentResult, approach: str) -> None:
    """Display decision trail for a specific approach.

    Args:
        tournament: Tournament result
        approach: Name of approach to show decisions for
    """
    result = tournament.get_result(approach)
    if not result:
        console.print(f"[red]Approach '{approach}' not found[/red]")
        return

    console.print(f"\n{'=' * 80}")
    console.print(f"[bold cyan]DECISION TRAIL: {approach}[/bold cyan]", justify="center")
    console.print(f"{'=' * 80}\n")

    if not result.decision_trail:
        console.print("[yellow]No decisions recorded[/yellow]")
        return

    for i, decision in enumerate(result.decision_trail, 1):
        mode_emoji = "⏸️" if decision.blocking else "⚡"
        mode_text = "BLOCKING" if decision.blocking else "SPECULATIVE"

        console.print(f"[bold]{i}. {decision.question}[/bold] [{mode_emoji} {mode_text}]")
        console.print(f"   Options: {', '.join(decision.options)}")
        console.print(f"   [green]Chosen:[/green] {decision.chosen}")
        console.print(f"   [dim]Reasoning:[/dim] {decision.reasoning}")
        console.print()


def print_code(tournament: TournamentResult, approach: str) -> None:
    """Display final code for a specific approach.

    Args:
        tournament: Tournament result
        approach: Name of approach to show code for
    """
    result = tournament.get_result(approach)
    if not result:
        console.print(f"[red]Approach '{approach}' not found[/red]")
        return

    console.print(f"\n{'=' * 80}")
    console.print(f"[bold cyan]SOLUTION CODE: {approach}[/bold cyan]", justify="center")
    console.print(f"{'=' * 80}\n")

    if not result.final_code:
        console.print("[yellow]No code available[/yellow]")
        return

    syntax = Syntax(result.final_code, "python", theme="monokai", line_numbers=True)
    console.print(syntax)
    console.print()


def print_progress(results: list[AgentResult], live: bool = True) -> None:
    """Display live progress during tournament execution.

    Args:
        results: Current agent results (may be incomplete)
        live: Whether to use live updates
    """
    # Simple ASCII progress display
    console.print("\n[bold cyan]Tournament Progress[/bold cyan]\n")

    for result in results:
        iteration = result.iteration_count
        final_iter = result.get_final_iteration()

        if final_iter:
            # Create progress bar
            total = final_iter.total_tests
            passed = final_iter.tests_passed
            bar_width = 20
            filled = int((passed / total) * bar_width) if total > 0 else 0
            bar = "█" * filled + "░" * (bar_width - filled)

            # Status
            if result.success:
                status = "✅ DONE"
                style = "green"
            else:
                error = final_iter.error_messages[0][:30] if final_iter.error_messages else "Working..."
                status = f"Fixing: {error}"
                style = "yellow"

            console.print(
                f"[bold]{result.approach:20}[/bold] │ "
                f"Iter {iteration:2} │ "
                f"{bar} │ "
                f"{passed}/{total} tests │ "
                f"[{style}]{status}[/{style}]"
            )
        else:
            console.print(
                f"[bold]{result.approach:20}[/bold] │ "
                f"Starting..."
            )

    console.print()


def save_winner(tournament: TournamentResult, output_path: Path | None = None) -> None:
    """Save winner's code to a file.

    Args:
        tournament: Tournament result
        output_path: Optional output path (default: winner.py)
    """
    if not tournament.winner:
        console.print("[red]No winner to save[/red]")
        return

    if output_path is None:
        output_path = Path("winner.py")

    output_path.write_text(tournament.winner.final_code)
    console.print(f"[green]✓[/green] Saved winner's code to {output_path}")


def prompt_confirmation(message: str, default: bool = True) -> bool:
    """Prompt user for yes/no confirmation.

    Args:
        message: Question to ask
        default: Default answer if user just presses enter

    Returns:
        True if user confirms, False otherwise
    """
    suffix = "[Y/n]" if default else "[y/N]"
    response = console.input(f"{message} {suffix} ")

    if not response:
        return default

    return response.lower() in ["y", "yes"]


def show_menu(options: list[str]) -> int:
    """Show an interactive menu and get user selection.

    Args:
        options: List of menu options

    Returns:
        Selected option index (0-based)
    """
    console.print("\n[bold]Options:[/bold]")
    for i, option in enumerate(options, 1):
        console.print(f"  {i}. {option}")

    while True:
        try:
            choice = console.input("\nSelect option: ")
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
            console.print(f"[red]Invalid choice. Please enter 1-{len(options)}[/red]")
        except ValueError:
            console.print("[red]Invalid input. Please enter a number.[/red]")


def print_error(message: str) -> None:
    """Print an error message.

    Args:
        message: Error message
    """
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a success message.

    Args:
        message: Success message
    """
    console.print(f"[bold green]✓[/bold green] {message}")


def print_warning(message: str) -> None:
    """Print a warning message.

    Args:
        message: Warning message
    """
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def show_spinner(message: str):
    """Show a spinner with a message.

    Args:
        message: Message to display

    Returns:
        Progress context manager
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )
    return progress
