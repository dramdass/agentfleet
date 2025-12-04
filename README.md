# AgentFleet

Multi-agent tournament system for comparing LLM implementation approaches in parallel.

## Overview

AgentFleet runs multiple AI agents simultaneously, each implementing a different approach to solve the same task. A supervisor agent designs blind evaluation criteria upfront, then agents compete to pass tests and optimize metrics. The system ranks approaches by weighted scores and surfaces the decision trail each agent made.

## Quick Start

```bash
# Install
pip install -e .

# Run tournament against a local repo (required)
agentfleet "Implement a rate limiter" "Token bucket" "Sliding window" "Fixed window" \
  --repo /Users/you/path/to/repo

# Run directly from GitHub (AgentFleet clones into ./work/repos/<slug>)
agentfleet "Add rate limiting" "Token bucket" "Sliding window" \
  --repo https://github.com/dramdass/flask-url-shortener.git

> `--repo` is required and must be either an absolute local path or a full GitHub URL.

# Interactive mode (pause at decisions)
agentfleet "Implement a rate limiter" "Token bucket" "Sliding window" --interactive

# Speculative mode (agents auto-decide, show trail after)
agentfleet "Implement a rate limiter" "Token bucket" "Sliding window" --yes
```

## How It Works

1. **Supervisor Plans**: Generates eval.py with tests, metrics, and scoring weights
2. **Agents Compete**: Each implements their approach, iterating until tests pass
3. **Decisions Recorded**: Every interpretive choice logged in decision trail
4. **Ranks Published**: Weighted scores determine winner, with full transparency

## Example Output

```
🥇 WINNER: Sliding window (95/100)

Decision Trail:
  1. Interpreted "per minute" as rolling window (speculative)
  2. Used list for timestamp storage over deque (speculative)
  3. Added thread safety via Lock (speculative)

Converged in 2 iterations. Simplest at 42 lines with perfect correctness.
```

## Git Worktrees

AgentFleet always targets a git repository. If you pass an absolute filesystem path we use it directly; if you pass a GitHub URL we clone it into `--work-dir/repos/<repo-slug>` and reuse that checkout on future runs. Every agent operates in its own worktree/branch:

```bash
# After tournament
cd your-repo
git worktree list                    # See all agent worktrees
git branch -a                        # See agent branches (agent/*)
git diff agent/sliding-window        # Compare with master
git checkout agent/token-bucket      # Inspect an approach
git merge agent/sliding-window       # Merge the winner
```

Typical review flow after a tournament:
- `cd /path/to/your/repo` (or the clone under `--work-dir/repos/...`)
- `git worktree list` to see all agent worktrees and check their filesystem locations
- `git branch -a | grep agent/` to see all agent branches
- `git checkout agent/sliding-window && pytest` to inspect and test an approach
- `git diff agent/sliding-window main` to review changes
- `git checkout main && git merge agent/sliding-window` to merge the winner

Worktrees persist after the tournament so you can diff, test, and merge whenever you're ready. Delete them with `git worktree remove <path>` once you're done.

## Architecture

- **planner.py**: Supervisor agent generates evaluation criteria
- **agent.py**: Agentic loop (implement → eval → fix)
- **tournament.py**: Parallel orchestration and ranking
- **models.py**: Data structures for plans, results, decisions
- **display.py**: Terminal output and progress bars
- **cli.py**: Entry point and argument parsing

## Examples

See `examples/` for complete demonstrations:

- **[URL Shortener Rate Limiting](examples/url-shortener-rate-limiting/)** - Add rate limiting to a Flask app, comparing Token Bucket, Sliding Window, and Fixed Window approaches
