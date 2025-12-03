# AgentFleet Technical Design Document

## Two-Paragraph Version

AgentFleet is a multi-agent tournament system that compares different implementation approaches to the same programming task. The system uses a supervisor agent to upfront design blind evaluation criteria (tests, metrics, scoring weights) before any code is written. Then, N agents run in parallel, each implementing a different approach (e.g., "token bucket" vs "sliding window" rate limiter). Each agent enters an agentic loop: write solution.py → run eval.py → see failures → fix → repeat until all tests pass or max iterations reached. Throughout execution, agents record every interpretive decision they make (how to handle ambiguities, what defaults to choose). After all agents complete, the system ranks approaches by weighted scores across correctness, simplicity, and performance categories, and surfaces the decision trail for transparency.

The key innovation is decision recording with speculative vs interactive modes. In speculative mode, agents autonomously resolve all ambiguities and record their reasoning for post-hoc review. In interactive mode, blocking decisions pause execution to prompt the human. This creates a spectrum from fully autonomous tournaments (fast, recordable, replayable) to human-in-the-loop guidance (slower, but can steer interpretations). The supervisor never sees implementation code—it only designs evaluation criteria from the task description. Agents never see each other's code—they only see their own test failures. This architectural separation ensures fair comparison: the evaluation is locked before execution, and each approach is judged by the same blind criteria.

## Full Technical Details

### Core Components

#### 1. Supervisor Planner (`planner.py`)

**Function**: `generate_plan(task: str, approaches: list[str]) -> Plan`

**Responsibilities**:
- Extract ambiguities from task description, generate clarifying questions with sensible defaults
- Define interface contract (exact class/method signatures agents must implement)
- Generate 4-6 deterministic tests mapped to scoring categories (correctness, edge cases, performance)
- Define 3-5 numeric metrics (test pass rate, lines of code, runtime complexity markers)
- Declare scoring weights that sum to 100%, locked before agent execution
- Output complete `eval.py` script that agents will iterate against

**Key Constraint**: Supervisor never sees implementation code. Evaluation criteria are designed blind.

**Prompt Template**:
```
You are designing evaluation criteria for a programming task. Multiple agents will implement different approaches, and you must create fair, deterministic tests to compare them.

Task: {task}
Approaches: {approaches}

Output a plan with:
1. Resolved task (clarify ambiguities with defaults)
2. Interface contract (exact signatures)
3. Tests (4-6 test cases with input/output/scoring category)
4. Metrics (3-5 numeric measures)
5. Weights (correctness %, simplicity %, performance %, sum to 100)
6. Complete eval.py script

Example eval.py structure:
```python
import sys
import json
from solution import RateLimiter

def run_tests():
    results = {"success": True, "tests": {}, "metrics": {}}

    # Test 1: Basic functionality (correctness)
    limiter = RateLimiter(limit=5, window=60)
    # ... test logic ...
    results["tests"]["test_basic"] = {"pass": True, "category": "correctness"}

    # ... more tests ...

    # Metrics
    results["metrics"]["lines_of_code"] = count_lines("solution.py")
    results["metrics"]["cyclomatic_complexity"] = estimate_complexity()

    return results

if __name__ == "__main__":
    results = run_tests()
    print(json.dumps(results))
    sys.exit(0 if results["success"] else 1)
```
```

#### 2. Agent Loop (`agent.py`)

**Function**: `run_agent_loop(plan: Plan, approach: str, work_dir: Path, max_iterations: int, on_decision_callback: Callable) -> AgentResult`

**Loop Flow**:
1. Agent receives: task, approach, interface contract, eval.py source
2. Agent writes `solution.py` in work_dir
3. Run `python eval.py solution.py`, capture JSON output
4. If tests fail: parse errors, decide what to fix, record decision if ambiguous, goto step 2
5. If tests pass: extract final metrics, return AgentResult
6. If max iterations reached: return partial result with failure status

**Decision Recording**:
- Every interpretive choice emits a `Decision` object
- Callback `on_decision_callback(decision)` allows UI to show or block for human input
- Decisions stored in `AgentResult.decision_trail`

**Prompt Template for Agent**:
```
You are implementing a solution using the {approach} approach.

Task: {resolved_task}
Interface contract:
{interface_contract}

You must write a file called solution.py that implements this interface.

Evaluation script (eval.py):
{eval_script}

Your solution will be tested by running:
  python eval.py solution.py

Current iteration: {iteration}/{max_iterations}

{previous_failure_info}

Write the complete solution.py file. If you make any interpretive decisions about ambiguous requirements, explain your reasoning.
```

**Decision Detection**:
- Parse agent output for phrases like "I interpreted...", "I chose...", "I assumed..."
- Extract: question, options considered, choice made, reasoning
- Determine if blocking (requires human input) or speculative (can proceed)

#### 3. Tournament Orchestrator (`tournament.py`)

**Function**: `run_tournament(task: str, approaches: list[str], plan: Plan, max_iterations: int, mode: str) -> TournamentResult`

**Modes**:
- `mode="speculative"`: Agents run fully autonomous, all decisions recorded for post-hoc review
- `mode="interactive"`: Agents pause at blocking decisions, prompt human for guidance

**Execution**:
```python
async def run_tournament(...):
    # Create isolated work directories
    work_dirs = [Path(f"work/{approach}") for approach in approaches]

    # Run all agents in parallel
    tasks = [
        run_agent_loop(plan, approach, work_dir, max_iterations, on_decision)
        for approach, work_dir in zip(approaches, work_dirs)
    ]
    results = await asyncio.gather(*tasks)

    # Compute scores
    scored_results = compute_scores(results, plan.weights)

    # Rank by weighted score
    ranked = sorted(scored_results, key=lambda r: r.score, reverse=True)

    return TournamentResult(results=ranked, plan=plan)
```

**Scoring Algorithm**:
```python
def compute_scores(results, weights):
    for result in results:
        if not result.success:
            # Failed agents only get simplicity/performance partial credit
            score = (
                weights["simplicity"] * result.metrics["simplicity_score"] +
                weights["performance"] * result.metrics["performance_score"]
            ) * 0.5  # Penalty factor
        else:
            # Passing agents get full weighted score
            score = (
                weights["correctness"] * result.metrics["correctness_score"] +
                weights["simplicity"] * result.metrics["simplicity_score"] +
                weights["performance"] * result.metrics["performance_score"]
            )
        result.score = score
    return results
```

#### 4. Data Models (`models.py`)

```python
@dataclass
class Decision:
    question: str           # "Should rate limiting be per-user or global?"
    options: list[str]      # ["per-user", "global"]
    chosen: str             # "per-user"
    reasoning: str          # Agent's explanation
    blocking: bool          # False = speculative, True = needs human
    timestamp: float

@dataclass
class Iteration:
    attempt: int
    tests_passed: int
    tests_failed: int
    decisions_made: list[Decision]
    error_messages: list[str]

@dataclass
class Plan:
    resolved_task: str
    interface_contract: str
    tests: list[dict]       # [{"name": str, "category": str, "weight": float}, ...]
    metrics: list[str]
    weights: dict           # {"correctness": 60, "simplicity": 25, "performance": 15}
    eval_script: str        # Complete eval.py source code

@dataclass
class AgentResult:
    approach: str
    success: bool
    iterations: list[Iteration]
    decision_trail: list[Decision]
    metrics: dict
    final_code: str
    score: float = 0.0

@dataclass
class TournamentResult:
    results: list[AgentResult]  # Sorted by score, descending
    plan: Plan
    winner: AgentResult = field(init=False)

    def __post_init__(self):
        self.winner = self.results[0] if self.results else None
```

#### 5. CLI and Display (`cli.py`, `display.py`)

**CLI Flow**:
```python
def main():
    parser = argparse.ArgumentParser(description="AgentFleet: Multi-agent tournament system")
    parser.add_argument("task", help="Programming task description")
    parser.add_argument("approaches", nargs="+", help="Approaches to compare (2-5)")
    parser.add_argument("--yes", action="store_true", help="Accept defaults, run speculative")
    parser.add_argument("--interactive", action="store_true", help="Pause at decisions")
    parser.add_argument("--max-iter", type=int, default=10, help="Max iterations per agent")
    parser.add_argument("--verbose", action="store_true", help="Show live progress")
    args = parser.parse_args()

    # Phase 1: Generate plan
    print("🔍 Generating evaluation plan...")
    plan = asyncio.run(generate_plan(args.task, args.approaches))
    print_plan(plan)

    if not args.yes:
        confirm = input("\nProceed with this plan? [Y/n] ")
        if confirm.lower() == "n":
            return

    # Phase 2: Run tournament
    mode = "interactive" if args.interactive else "speculative"
    print(f"\n🚀 Starting tournament ({mode} mode)...")
    result = asyncio.run(run_tournament(args.task, args.approaches, plan, args.max_iter, mode))

    # Phase 3: Display results
    print_results(result)

    # Phase 4: Interactive menu
    while True:
        choice = input("\nView [c]ode, [d]ecisions, [s]ave winner, or [q]uit? ")
        if choice == "c":
            approach = input("Which approach? ")
            print_code(result, approach)
        elif choice == "d":
            approach = input("Which approach? ")
            print_decisions(result, approach)
        elif choice == "s":
            save_winner(result)
        elif choice == "q":
            break
```

**Display Functions**:

```python
def print_plan(plan: Plan):
    """Show evaluation plan before execution"""
    print("\n" + "="*80)
    print("EVALUATION PLAN")
    print("="*80)
    print(f"\nResolved Task:\n{plan.resolved_task}\n")
    print(f"Interface Contract:\n{plan.interface_contract}\n")
    print("Tests:")
    for test in plan.tests:
        print(f"  - {test['name']} ({test['category']}, {test['weight']}%)")
    print("\nMetrics:")
    for metric in plan.metrics:
        print(f"  - {metric}")
    print("\nScoring Weights:")
    for category, weight in plan.weights.items():
        print(f"  - {category}: {weight}%")

def print_progress(results: list[AgentResult], live: bool = True):
    """Show live progress during tournament"""
    # Use rich.progress or simple ASCII
    for result in results:
        iterations = len(result.iterations)
        latest = result.iterations[-1] if result.iterations else None
        if latest:
            bar = "█" * (latest.tests_passed * 2) + "░" * (latest.tests_failed * 2)
            status = "✅ DONE" if result.success else f"Fixing {latest.error_messages[0][:20]}..."
            print(f"{result.approach:20} │ Iter {iterations:2} │ {bar:20} │ {latest.tests_passed}/{latest.tests_passed + latest.tests_failed} tests │ {status}")

def print_results(tournament: TournamentResult):
    """Show final rankings and scores"""
    print("\n" + "="*80)
    print("TOURNAMENT RESULTS")
    print("="*80)

    for i, result in enumerate(tournament.results):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
        print(f"\n{medal} {result.approach.upper()} ({result.score:.1f}/100)")
        print(f"   Status: {'✅ PASSED' if result.success else '❌ FAILED'}")
        print(f"   Iterations: {len(result.iterations)}")
        print(f"   Metrics: {result.metrics}")
        if result.decision_trail:
            print(f"   Decisions: {len(result.decision_trail)} interpretive choices")

def print_decisions(tournament: TournamentResult, approach: str):
    """Show decision trail for an approach"""
    result = next((r for r in tournament.results if r.approach == approach), None)
    if not result:
        print(f"Approach '{approach}' not found")
        return

    print(f"\n{'='*80}")
    print(f"DECISION TRAIL: {approach}")
    print(f"{'='*80}\n")

    for i, decision in enumerate(result.decision_trail, 1):
        blocking = "⏸️ BLOCKING" if decision.blocking else "⚡ SPECULATIVE"
        print(f"{i}. {decision.question} [{blocking}]")
        print(f"   Options: {', '.join(decision.options)}")
        print(f"   Chosen: {decision.chosen}")
        print(f"   Reasoning: {decision.reasoning}\n")
```

### Eval Script Contract

**Input**: `sys.argv[1]` contains path to solution.py

**Output**: JSON to stdout with structure:
```json
{
  "success": true,
  "tests": {
    "test_basic": {"pass": true, "category": "correctness", "message": ""},
    "test_boundary": {"pass": false, "category": "correctness", "message": "Expected False, got True"},
    "test_thread_safety": {"pass": true, "category": "performance", "message": ""}
  },
  "metrics": {
    "correctness_score": 0.8,
    "simplicity_score": 0.9,
    "performance_score": 0.7,
    "lines_of_code": 45,
    "cyclomatic_complexity": 7
  }
}
```

**Exit Code**: 0 if all tests pass, 1 if any fail

### Demo Repository Structure

```
agentfleet-demo-ratelimiter/
├── README.md                      # Explains the challenge and expected results
├── reference/
│   ├── token_bucket.py            # Clean reference implementation
│   ├── sliding_window.py          # Clean reference implementation
│   └── fixed_window.py            # Has intentional boundary bug
└── eval/
    └── eval_example.py            # Example of supervisor output
```

**Demo README Content**:
```markdown
# AgentFleet Demo: Rate Limiter Comparison

This demo compares three approaches to implementing a rate limiter.

## The Challenge

Implement a rate limiter that allows at most N requests per time window.

Requirements:
- Must track requests per user
- Must handle boundary cases (exactly N requests, window expiry)
- Should be thread-safe for production use
- Should be simple and maintainable

## Approaches

1. **Token Bucket**: Accumulates tokens over time, spends on requests
2. **Sliding Window**: Tracks exact timestamps, rolls window continuously
3. **Fixed Window**: Resets counter at fixed intervals (has boundary bug!)

## Expected Results

When you run:
```bash
agentfleet "Implement rate limiter allowing 5 requests per minute per user" \
           "Token bucket" "Sliding window" "Fixed window"
```

Expected winner: **Sliding window** (95/100)
- Passes all tests including boundary cases
- Simplest implementation (~42 lines)
- Most accurate rate limiting

Fixed window should fail the boundary test due to allowing 2x requests at window edge.

## Reference Implementations

The `reference/` directory contains human-written implementations for comparison.
These are NOT used by agents—they implement from scratch based on approach name.

## Running Manually

You can test the eval script directly:
```bash
python eval/eval_example.py reference/sliding_window.py
```
```

### Testing Strategy

1. **Unit Tests** (`tests/test_models.py`):
   - Test dataclass creation and serialization
   - Test Decision, Iteration, Plan, AgentResult, TournamentResult

2. **Integration Tests** (`tests/test_integration.py`):
   - Test supervisor plan generation with mock task
   - Test single agent loop with mock eval.py
   - Test tournament with 2 approaches

3. **End-to-End Test**:
   - Run full tournament on demo rate limiter task
   - Verify sliding window wins
   - Verify fixed window fails boundary test
   - Verify decision trails are recorded

### Dependencies and Environment

**Python Version**: >=3.10 (for dataclasses, match statements, async)

**Required Packages**:
- `anthropic>=0.39.0` — Claude API client
- `prompt_toolkit>=3.0.0` — Interactive CLI with tab completion
- `rich>=13.0.0` — Pretty terminal output (tables, progress bars)

**Environment Variables**:
- `ANTHROPIC_API_KEY` — Required for Claude API access
- `AGENTFLEET_MODEL` — Optional, defaults to "claude-sonnet-4-20250514"
- `AGENTFLEET_MAX_TOKENS` — Optional, defaults to 4096

### Key Design Decisions

1. **Supervisor Blindness**: Evaluation criteria designed before seeing any code ensures fairness
2. **Agent Isolation**: Agents never see each other's implementations, only their own test results
3. **Decision Recording**: All interpretive choices logged for transparency and post-hoc review
4. **Parallel Execution**: Agents run simultaneously for speed, isolated in separate work directories
5. **Weighted Scoring**: Categories (correctness, simplicity, performance) weighted upfront by supervisor
6. **Speculative vs Interactive**: Spectrum from fully autonomous to human-in-the-loop
7. **Deterministic Evaluation**: eval.py is deterministic, reproducible across runs

### Future Enhancements

- **Multi-round Tournaments**: Agents observe winner's decisions, retry with new insights
- **Hybrid Approaches**: Allow agents to propose combining aspects of multiple approaches
- **Dynamic Weighting**: Learn optimal weights from human preference feedback
- **Cost Tracking**: Report token usage and API costs per agent
- **Conversation Replay**: Save/load tournament state for analysis
- **Web UI**: Browser-based interface for watching tournaments live
