"""Agentic implementation loop for individual agents."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Any

from anthropic import Anthropic

from agentfleet.models import AgentResult, Decision, Iteration, Plan
from agentfleet.git_utils import format_agent_branch
from agentfleet.prompts import (
    format_agent_prompt,
    format_decision_extraction_prompt,
)


async def run_agent_loop(
    plan: Plan,
    approach: str,
    work_dir: Path,
    max_iterations: int = 10,
    source_repo: Path | None = None,
    on_decision_callback: Callable[[Decision], None] | None = None,
) -> AgentResult:
    """Run the agentic implementation loop for a single approach.

    The agent follows this loop:
    1. Generate solution.py
    2. Run eval.py against it
    3. If tests fail: analyze errors, fix, repeat
    4. If tests pass: done
    5. Record all decisions made

    Args:
        plan: Evaluation plan from supervisor
        approach: Name of approach to implement
        work_dir: Directory to work in (isolated per agent)
        max_iterations: Maximum number of fix iterations
        source_repo: Optional path to source repository to copy into work_dir
        on_decision_callback: Optional callback for decision events

    Returns:
        AgentResult with success status, iterations, decisions, metrics
    """
    # Setup
    branch_name: str | None = None
    if source_repo:
        # Create git worktree (will create work_dir)
        branch_name = _copy_source_repo(source_repo, work_dir, approach)
    else:
        # No source repo, just create work directory
        work_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    model = os.getenv("AGENTFLEET_MODEL", "claude-sonnet-4-20250514")
    client = Anthropic(api_key=api_key)

    # Write eval.py to work directory
    eval_path = work_dir / "eval.py"
    eval_path.write_text(plan.eval_script)

    # Initialize tracking
    iterations: list[Iteration] = []
    all_decisions: list[Decision] = []
    current_code = ""
    previous_status = "None"
    failure_info = ""

    # Iteration loop
    for iteration_num in range(1, max_iterations + 1):
        # Generate/fix solution
        try:
            prompt = format_agent_prompt(
                approach=approach,
                resolved_task=plan.resolved_task,
                interface_contract=plan.interface_contract,
                eval_script=plan.eval_script,
                iteration=iteration_num,
                max_iterations=max_iterations,
                previous_status=previous_status,
                failure_info=failure_info,
            )

            response = client.messages.create(
                model=model,
                max_tokens=int(os.getenv("AGENTFLEET_MAX_TOKENS", "8192")),
                messages=[{"role": "user", "content": prompt}],
            )

            agent_output = response.content[0].text

            # Extract code from response
            code = _extract_code_from_response(agent_output)
            current_code = code

            # Write solution.py
            solution_path = work_dir / "solution.py"
            solution_path.write_text(code)

            # Extract decisions from agent output
            decisions = await _extract_decisions(client, model, agent_output)
            for decision in decisions:
                if on_decision_callback:
                    on_decision_callback(decision)
            all_decisions.extend(decisions)

        except Exception as e:
            # Agent crashed during generation
            return AgentResult(
                approach=approach,
                success=False,
                iterations=iterations,
                decision_trail=all_decisions,
                metrics={},
                final_code=current_code,
                work_dir=str(work_dir),
                branch_name=branch_name,
                error=f"Code generation failed: {e}",
            )

        # Run evaluation
        eval_result = _run_evaluation(work_dir, solution_path)

        # Record iteration
        iteration = Iteration(
            attempt=iteration_num,
            tests_passed=eval_result["tests_passed"],
            tests_failed=eval_result["tests_failed"],
            decisions_made=decisions,
            error_messages=eval_result["error_messages"],
            code_snapshot=code,
        )
        iterations.append(iteration)

        # Check if successful
        if eval_result["success"]:
            return AgentResult(
                approach=approach,
                success=True,
                iterations=iterations,
                decision_trail=all_decisions,
                metrics=eval_result["metrics"],
                final_code=current_code,
                work_dir=str(work_dir),
                branch_name=branch_name,
            )

        # Prepare for next iteration
        previous_status = f"Failed {eval_result['tests_failed']}/{eval_result['tests_passed'] + eval_result['tests_failed']} tests"
        failure_info = _format_failure_info(eval_result)

    # Max iterations reached without success
    return AgentResult(
        approach=approach,
        success=False,
        iterations=iterations,
        decision_trail=all_decisions,
        metrics=iterations[-1].error_messages if iterations else {},
        final_code=current_code,
        work_dir=str(work_dir),
        branch_name=branch_name,
        error=f"Max iterations ({max_iterations}) reached without passing all tests",
    )


def _extract_code_from_response(response: str) -> str:
    """Extract Python code from Claude's response.

    Args:
        response: Raw response text

    Returns:
        Extracted code

    Raises:
        ValueError: If no code found
    """
    # Look for code blocks
    if "```python" in response:
        start = response.find("```python") + 9
        end = response.find("```", start)
        return response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        return response[start:end].strip()
    else:
        # Maybe the whole response is code?
        # Look for class or def keywords
        if "class " in response or "def " in response:
            return response.strip()
        raise ValueError("No code block found in response")


async def _extract_decisions(
    client: Anthropic, model: str, agent_output: str
) -> list[Decision]:
    """Extract decisions from agent's output using Claude.

    Args:
        client: Anthropic client
        model: Model name
        agent_output: Agent's response text

    Returns:
        List of Decision objects
    """
    try:
        prompt = format_decision_extraction_prompt(agent_output)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        decision_text = response.content[0].text

        # Extract JSON
        if "```json" in decision_text:
            start = decision_text.find("```json") + 7
            end = decision_text.find("```", start)
            json_str = decision_text[start:end].strip()
        elif "```" in decision_text:
            start = decision_text.find("```") + 3
            end = decision_text.find("```", start)
            json_str = decision_text[start:end].strip()
        else:
            start = decision_text.find("[")
            end = decision_text.rfind("]") + 1
            if start == -1 or end == 0:
                return []
            json_str = decision_text[start:end]

        decisions_data = json.loads(json_str)

        # Convert to Decision objects
        return [
            Decision(
                question=d["question"],
                options=d["options"],
                chosen=d["chosen"],
                reasoning=d["reasoning"],
                blocking=d.get("blocking", False),
            )
            for d in decisions_data
        ]

    except Exception:
        # If extraction fails, return empty list
        return []


def _run_evaluation(work_dir: Path, solution_path: Path) -> dict[str, Any]:
    """Run eval.py against solution.py and parse results.

    Args:
        work_dir: Working directory containing eval.py
        solution_path: Path to solution.py

    Returns:
        Dictionary with evaluation results
    """
    eval_path = work_dir / "eval.py"

    try:
        # Run eval.py with solution path as argument
        result = subprocess.run(
            [sys.executable, str(eval_path), str(solution_path)],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Parse JSON output
        try:
            eval_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Eval script didn't output valid JSON
            return {
                "success": False,
                "tests_passed": 0,
                "tests_failed": 1,
                "error_messages": [f"Eval script output invalid JSON: {result.stdout}"],
                "metrics": {},
            }

        # Extract test results
        tests = eval_data.get("tests", {})
        tests_passed = sum(1 for t in tests.values() if t.get("pass", False))
        tests_failed = len(tests) - tests_passed

        # Extract error messages
        error_messages = [
            f"{name}: {test.get('message', 'Failed')}"
            for name, test in tests.items()
            if not test.get("pass", False)
        ]

        # If subprocess failed but JSON was valid, it means tests failed
        success = eval_data.get("success", False) and result.returncode == 0

        return {
            "success": success,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "error_messages": error_messages,
            "metrics": eval_data.get("metrics", {}),
            "tests": tests,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "tests_passed": 0,
            "tests_failed": 1,
            "error_messages": ["Evaluation timed out after 30 seconds"],
            "metrics": {},
        }
    except Exception as e:
        return {
            "success": False,
            "tests_passed": 0,
            "tests_failed": 1,
            "error_messages": [f"Evaluation error: {e}"],
            "metrics": {},
        }


def _format_failure_info(eval_result: dict[str, Any]) -> str:
    """Format failure information for next iteration prompt.

    Args:
        eval_result: Results from evaluation

    Returns:
        Formatted failure information string
    """
    if not eval_result["error_messages"]:
        return ""

    failures = "\n".join(f"- {msg}" for msg in eval_result["error_messages"])
    return f"""
**Previous Iteration Failed:**

Failed Tests:
{failures}

Please analyze these failures and fix the issues in your solution.
"""


def _copy_source_repo(source_repo: Path, work_dir: Path, approach: str) -> str:
    """Create a git worktree for the agent to work in.

    Args:
        source_repo: Path to source git repository
        work_dir: Destination work directory (will be created as worktree)
        approach: Approach name (used for branch naming)

    Raises:
        FileNotFoundError: If source_repo doesn't exist
        ValueError: If source_repo is not a git repository
    """
    repo_path = source_repo.expanduser().resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Source repository not found: {repo_path}")

    git_dir = repo_path / ".git"
    if not git_dir.exists():
        raise ValueError(f"Source repository is not a git repository: {repo_path}")

    worktree_path = work_dir.expanduser().resolve()
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)

    branch_name = format_agent_branch(approach)

    def _run_git(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=check,
            )
        except FileNotFoundError:
            raise ValueError("git executable not found. Cannot manage worktrees.") from None

    def _format_error(extra: str | None = None) -> str:
        base = f"Failed to create git worktree '{branch_name}' in {repo_path}"
        return f"{base}: {extra}" if extra else base

    try:
        _run_git(["git", "worktree", "add", "-b", branch_name, str(worktree_path)])
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").lower()
        if "already exists" in stderr or "worktree add" in stderr:
            _run_git(["git", "branch", "-D", branch_name], check=False)
            _run_git(["git", "worktree", "remove", str(worktree_path), "--force"], check=False)
            shutil.rmtree(worktree_path, ignore_errors=True)
            try:
                _run_git(["git", "worktree", "add", "-b", branch_name, str(worktree_path)])
            except subprocess.CalledProcessError as retry_error:
                detail = retry_error.stderr.strip() if retry_error.stderr else None
                raise ValueError(_format_error(detail)) from retry_error
        else:
            detail = e.stderr.strip() if e.stderr else None
            raise ValueError(_format_error(detail)) from e

    return branch_name
