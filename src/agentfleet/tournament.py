"""Tournament orchestration for parallel agent execution."""

import asyncio
from pathlib import Path
from typing import Callable

from agentfleet.agent import run_agent_loop
from agentfleet.models import AgentResult, Decision, Plan, TournamentResult


async def run_tournament(
    task: str,
    approaches: list[str],
    plan: Plan,
    max_iterations: int = 10,
    mode: str = "speculative",
    work_base_dir: Path | None = None,
    source_repo: Path | None = None,
    on_progress_callback: Callable[[str, int, bool], None] | None = None,
) -> TournamentResult:
    """Run a tournament with multiple agents in parallel.

    Each agent runs in isolation, implementing their assigned approach.
    After all agents complete, results are scored and ranked.

    Args:
        task: Original task description
        approaches: List of approach names
        plan: Evaluation plan from supervisor
        max_iterations: Max iterations per agent
        mode: "speculative" (auto-decide) or "interactive" (pause for decisions)
        work_base_dir: Base directory for agent workspaces
        source_repo: Optional path to source repository to copy to each agent's workspace
        on_progress_callback: Callback(approach, iteration, success) for live updates

    Returns:
        TournamentResult with ranked results

    Raises:
        ValueError: If fewer than 2 approaches provided
    """
    if len(approaches) < 2:
        raise ValueError("Tournament requires at least 2 approaches")

    if source_repo is None:
        raise ValueError("A git repository is required. Provide --repo with a valid path or URL.")

    source_repo = source_repo.expanduser().resolve()
    if not source_repo.exists():
        raise ValueError(f"Source repository not found: {source_repo}")

    # Setup work directories
    if work_base_dir is None:
        work_base_dir = Path.cwd() / "work"

    work_base_dir = work_base_dir.expanduser().resolve()
    work_base_dir.mkdir(parents=True, exist_ok=True)

    work_dirs = [work_base_dir / approach.replace(" ", "_") for approach in approaches]

    # Create decision callback based on mode
    decision_callback = _create_decision_callback(mode)

    # Run all agents in parallel
    tasks = [
        run_agent_loop(
            plan=plan,
            approach=approach,
            work_dir=work_dir,
            max_iterations=max_iterations,
            source_repo=source_repo,
            on_decision_callback=decision_callback,
        )
        for approach, work_dir in zip(approaches, work_dirs)
    ]

    # Execute with progress tracking
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions
    agent_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # Agent crashed, create error result
            agent_results.append(
                AgentResult(
                    approach=approaches[i],
                    success=False,
                    iterations=[],
                    decision_trail=[],
                    metrics={},
                    final_code="",
                    work_dir=str(work_dirs[i]),
                    error=str(result),
                )
            )
        else:
            agent_results.append(result)

    # Compute scores
    scored_results = compute_scores(agent_results, plan)

    # Create tournament result (will auto-sort by score)
    return TournamentResult(results=scored_results, plan=plan)


def compute_scores(results: list[AgentResult], plan: Plan) -> list[AgentResult]:
    """Compute weighted scores for all results.

    Scoring rules:
    - Only passing agents get full category scores
    - Failed agents get partial credit (50% of simplicity/performance)
    - Scores are weighted by plan.weights

    Args:
        results: List of agent results
        plan: Evaluation plan with weights

    Returns:
        List of results with scores computed
    """
    for result in results:
        if result.success:
            # Full weighted score for passing agents
            score = _compute_weighted_score(result.metrics, plan.weights)
        else:
            # Partial credit for failed agents
            # Only count simplicity and performance at 50% weight
            partial_metrics = {
                "correctness_score": 0.0,
                "simplicity_score": result.metrics.get("simplicity_score", 0.0) * 0.5,
                "performance_score": result.metrics.get("performance_score", 0.0) * 0.5,
            }
            score = _compute_weighted_score(partial_metrics, plan.weights)

        result.score = score

    return results


def _compute_weighted_score(metrics: dict, weights: dict[str, float]) -> float:
    """Compute weighted score from metrics.

    Args:
        metrics: Dictionary of metric values (e.g., {"correctness_score": 0.9})
        weights: Dictionary of weights (e.g., {"correctness": 60})

    Returns:
        Weighted score (0-100)
    """
    score = 0.0

    # Map metric names to weight categories
    metric_to_category = {
        "correctness_score": "correctness",
        "simplicity_score": "simplicity",
        "performance_score": "performance",
    }

    for metric_name, category in metric_to_category.items():
        metric_value = metrics.get(metric_name, 0.0)
        weight = weights.get(category, 0.0)
        score += metric_value * weight

    return score


def _create_decision_callback(mode: str) -> Callable[[Decision], None] | None:
    """Create decision callback based on mode.

    Args:
        mode: "speculative" or "interactive"

    Returns:
        Callback function or None
    """
    if mode == "interactive":
        # Interactive mode: pause and prompt user
        def interactive_callback(decision: Decision) -> None:
            if decision.blocking:
                print(f"\n⏸️  Decision required: {decision.question}")
                print(f"Options: {', '.join(decision.options)}")
                print(f"Agent suggests: {decision.chosen}")
                print(f"Reasoning: {decision.reasoning}")

                response = input("Accept suggestion? [Y/n] ")
                if response.lower() == "n":
                    # Let user choose
                    print("Available options:")
                    for i, opt in enumerate(decision.options, 1):
                        print(f"  {i}. {opt}")
                    choice_idx = int(input("Select option (number): ")) - 1
                    decision.chosen = decision.options[choice_idx]

        return interactive_callback

    # Speculative mode: just record decisions, don't block
    return None


async def run_tournament_with_live_updates(
    task: str,
    approaches: list[str],
    plan: Plan,
    max_iterations: int = 10,
    mode: str = "speculative",
    display_callback: Callable[[list[AgentResult]], None] | None = None,
    source_repo: Path | None = None,
) -> TournamentResult:
    """Run tournament with live progress updates.

    This is an alternative to run_tournament that provides real-time
    progress updates via a callback.

    Args:
        task: Task description
        approaches: List of approaches
        plan: Evaluation plan
        max_iterations: Max iterations per agent
        mode: "speculative" or "interactive"
        display_callback: Callback for displaying progress
        source_repo: Absolute path to the validated git repository

    Returns:
        TournamentResult with rankings
    """
    # Start tournament
    tournament_task = asyncio.create_task(
        run_tournament(
            task=task,
            approaches=approaches,
            plan=plan,
            max_iterations=max_iterations,
            mode=mode,
            source_repo=source_repo,
        )
    )

    # Poll for updates while tournament runs
    if display_callback:
        while not tournament_task.done():
            await asyncio.sleep(1)
            # In a real implementation, we'd track progress per agent
            # For now, this is a placeholder

    # Wait for completion
    return await tournament_task


def get_medal(rank: int) -> str:
    """Get medal emoji for ranking.

    Args:
        rank: 1-indexed rank

    Returns:
        Medal emoji or rank number
    """
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"{rank}."


def format_score(score: float) -> str:
    """Format score for display.

    Args:
        score: Score value (0-100)

    Returns:
        Formatted score string
    """
    return f"{score:.1f}/100"
