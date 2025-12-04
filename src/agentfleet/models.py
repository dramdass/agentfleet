"""Core data models for AgentFleet tournament system."""

from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class Decision:
    """Records a decision point where an agent made an interpretive choice.

    Attributes:
        question: The ambiguity or choice being resolved
        options: List of possible choices considered
        chosen: The option that was selected
        reasoning: Agent's explanation for the choice
        blocking: If True, required human input; if False, was speculative
        timestamp: When the decision was made (seconds since epoch)
    """

    question: str
    options: list[str]
    chosen: str
    reasoning: str
    blocking: bool = False
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        mode = "BLOCKING" if self.blocking else "SPECULATIVE"
        return f"Decision({mode}: {self.question} -> {self.chosen})"


@dataclass
class Iteration:
    """Records one cycle of the agent's implementation loop.

    Attributes:
        attempt: Iteration number (1-indexed)
        tests_passed: Number of tests that passed
        tests_failed: Number of tests that failed
        decisions_made: Decisions recorded during this iteration
        error_messages: Error messages from failed tests
        code_snapshot: Optional snapshot of code at this iteration
    """

    attempt: int
    tests_passed: int
    tests_failed: int
    decisions_made: list[Decision] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)
    code_snapshot: str | None = None

    @property
    def total_tests(self) -> int:
        """Total number of tests run."""
        return self.tests_passed + self.tests_failed

    @property
    def success(self) -> bool:
        """Whether all tests passed in this iteration."""
        return self.tests_failed == 0 and self.tests_passed > 0


@dataclass
class Plan:
    """Supervisor's evaluation plan, designed blind to implementations.

    Attributes:
        resolved_task: Task description with ambiguities clarified
        interface_contract: Exact class/method signatures to implement
        tests: List of test definitions with categories
        metrics: List of metric names to measure
        weights: Scoring weights by category (must sum to 100)
        eval_script: Complete eval.py source code
    """

    resolved_task: str
    interface_contract: str
    tests: list[dict[str, Any]]
    metrics: list[str]
    weights: dict[str, float]
    eval_script: str

    def __post_init__(self):
        """Validate that weights sum to 100."""
        total = sum(self.weights.values())
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Weights must sum to 100, got {total}")

    @property
    def test_count(self) -> int:
        """Total number of tests in the plan."""
        return len(self.tests)

    def get_category_weight(self, category: str) -> float:
        """Get weight for a scoring category."""
        return self.weights.get(category, 0.0)


@dataclass
class AgentResult:
    """Final result from a single agent's tournament run.

    Attributes:
        approach: Name of the approach being implemented
        success: Whether the agent passed all tests
        iterations: List of all iteration records
        decision_trail: All decisions made across iterations
        metrics: Final metric values
        final_code: The solution code that was produced
        work_dir: Path to agent's working directory
        score: Weighted score (computed after tournament)
        error: Optional error message if agent crashed
    """

    approach: str
    success: bool
    iterations: list[Iteration]
    decision_trail: list[Decision]
    metrics: dict[str, Any]
    final_code: str
    work_dir: str
    branch_name: str | None = None
    score: float = 0.0
    error: str | None = None

    @property
    def iteration_count(self) -> int:
        """Number of iterations the agent took."""
        return len(self.iterations)

    @property
    def decision_count(self) -> int:
        """Number of decisions recorded."""
        return len(self.decision_trail)

    @property
    def converged(self) -> bool:
        """Whether agent successfully converged to a solution."""
        return self.success and len(self.iterations) > 0

    def get_final_iteration(self) -> Iteration | None:
        """Get the last iteration, if any."""
        return self.iterations[-1] if self.iterations else None


@dataclass
class TournamentResult:
    """Aggregated results from a complete tournament run.

    Attributes:
        results: List of agent results, sorted by score (descending)
        plan: The evaluation plan used
        timestamp: When the tournament completed
    """

    results: list[AgentResult]
    plan: Plan
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        """Ensure results are sorted by score."""
        self.results.sort(key=lambda r: r.score, reverse=True)

    @property
    def winner(self) -> AgentResult | None:
        """The winning agent (highest score)."""
        return self.results[0] if self.results else None

    @property
    def approaches(self) -> list[str]:
        """List of all approaches that competed."""
        return [r.approach for r in self.results]

    def get_result(self, approach: str) -> AgentResult | None:
        """Get result for a specific approach."""
        return next((r for r in self.results if r.approach == approach), None)

    def get_top_n(self, n: int) -> list[AgentResult]:
        """Get top N results by score."""
        return self.results[:n]
