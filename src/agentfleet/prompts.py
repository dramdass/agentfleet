"""Prompt templates for supervisor and agent interactions."""

SUPERVISOR_PLAN_PROMPT = """You are designing evaluation criteria for a programming task. Multiple AI agents will implement different approaches in parallel, and you must create fair, deterministic tests to compare them.

Your role is to design the evaluation BEFORE seeing any implementation code. This ensures unbiased, fair comparison.

**Task Description:**
{task}

**Approaches to Compare:**
{approaches}

**Your Goal:**
Create a complete evaluation plan with the following components:

1. **Resolved Task**: Clarify any ambiguities in the task description with sensible defaults. If the task is vague about requirements, make explicit decisions about what "correct" means.

2. **Interface Contract**: Define the exact class and method signatures that all agents must implement. Be specific about:
   - Class names
   - Method names and parameters
   - Return types
   - Expected behavior

3. **Tests**: Design 4-6 deterministic test cases that will be used to evaluate implementations. For each test:
   - Give it a clear name (e.g., "test_basic_functionality")
   - Specify the input/output or behavior being tested
   - Assign it to a category: "correctness", "edge_cases", or "performance"
   - Ensure tests are deterministic and can be automated

4. **Metrics**: Define 3-5 numeric metrics to measure, such as:
   - Correctness score (0-1, based on test pass rate)
   - Simplicity score (0-1, based on lines of code, cyclomatic complexity)
   - Performance score (0-1, based on runtime, memory usage)

5. **Scoring Weights**: Assign percentage weights to categories that sum to exactly 100:
   - correctness: X%
   - simplicity: Y%
   - performance: Z%

   These weights will determine the final ranking.

6. **Complete eval.py Script**: Write a fully executable Python script that:
   - Takes solution file path as sys.argv[1]
   - Imports the solution and runs all tests
   - Computes all metrics
   - Outputs JSON with this exact structure:
   ```json
   {{
     "success": true/false,
     "tests": {{
       "test_name": {{"pass": true/false, "category": "correctness/edge_cases/performance", "message": "details"}}
     }},
     "metrics": {{
       "correctness_score": 0.0-1.0,
       "simplicity_score": 0.0-1.0,
       "performance_score": 0.0-1.0,
       "lines_of_code": int,
       "cyclomatic_complexity": int
     }}
   }}
   ```
   - Exits with code 0 if all tests pass, 1 if any fail

**Output Format:**
Return your plan as a JSON object with these keys:
- resolved_task: string
- interface_contract: string
- tests: list of {{"name": str, "category": str, "description": str}}
- metrics: list of strings
- weights: {{"correctness": float, "simplicity": float, "performance": float}}
- eval_script: string (complete Python code)

**Important Constraints:**
- Never assume you'll see the implementation code—design criteria blind
- Make tests deterministic and reproducible
- Weights must sum to exactly 100
- eval.py must be fully self-contained and executable
- Be fair to all approaches—don't bias toward any specific implementation style

Generate the evaluation plan now."""

AGENT_IMPLEMENTATION_PROMPT = """You are implementing a programming solution using the **{approach}** approach.

**Task:**
{resolved_task}

**Interface Contract:**
You must implement exactly this interface:
{interface_contract}

**Evaluation:**
Your solution will be tested by running this evaluation script:

```python
{eval_script}
```

The eval script will:
1. Import your solution from solution.py
2. Run all tests
3. Compute metrics
4. Return JSON with pass/fail results

**Current Status:**
- Iteration: {iteration}/{max_iterations}
- Previous attempt: {previous_status}

{failure_info}

**Your Task:**
Write a complete solution.py file that implements the interface contract using the {approach} approach.

**Decision Recording:**
If you need to make any interpretive decisions about ambiguous requirements:
1. Clearly state the question you're resolving
2. List the options you considered
3. Explain which option you chose and why
4. Proceed with your chosen interpretation

For example:
"DECISION: Should rate limiting be per-user or global?
OPTIONS: [per-user, global]
CHOSEN: per-user
REASONING: The interface contract includes a user_id parameter, implying per-user tracking."

**Output:**
Provide the complete solution.py file content. If this is a fix iteration, focus on addressing the test failures while preserving working functionality."""

AGENT_FIX_PROMPT = """Your previous solution had test failures. Here are the details:

**Failed Tests:**
{failed_tests}

**Error Messages:**
{error_messages}

**Your Current Code:**
```python
{current_code}
```

**Instructions:**
Analyze the failures and fix the issues. Make only the necessary changes to pass the failing tests while preserving functionality that already works.

If you need to make any design decisions to fix the issues, use the DECISION format:
- State the question
- List options
- Explain your choice

Provide the complete updated solution.py file."""

DECISION_EXTRACTION_PROMPT = """Analyze the agent's output and extract any interpretive decisions they made.

**Agent Output:**
{agent_output}

**Look for phrases like:**
- "I interpreted..."
- "I chose..."
- "I assumed..."
- "I decided to..."
- "DECISION:"

**For each decision found, extract:**
1. The question or ambiguity being resolved
2. Options that were considered
3. The choice that was made
4. The reasoning provided

**Output format:**
Return a JSON list of decisions:
```json
[
  {{
    "question": "Should rate limiting be per-user or global?",
    "options": ["per-user", "global"],
    "chosen": "per-user",
    "reasoning": "Task mentions user_id parameter",
    "blocking": false
  }}
]
```

If no decisions were found, return an empty list: []

**Agent Output:**
{agent_output}

Extract decisions now."""


def format_supervisor_prompt(task: str, approaches: list[str]) -> str:
    """Format the supervisor planning prompt."""
    approaches_str = "\n".join(f"- {approach}" for approach in approaches)
    return SUPERVISOR_PLAN_PROMPT.format(task=task, approaches=approaches_str)


def format_agent_prompt(
    approach: str,
    resolved_task: str,
    interface_contract: str,
    eval_script: str,
    iteration: int,
    max_iterations: int,
    previous_status: str = "None",
    failure_info: str = "",
) -> str:
    """Format the agent implementation prompt."""
    return AGENT_IMPLEMENTATION_PROMPT.format(
        approach=approach,
        resolved_task=resolved_task,
        interface_contract=interface_contract,
        eval_script=eval_script,
        iteration=iteration,
        max_iterations=max_iterations,
        previous_status=previous_status,
        failure_info=failure_info,
    )


def format_fix_prompt(
    failed_tests: list[dict],
    error_messages: list[str],
    current_code: str,
) -> str:
    """Format the agent fix iteration prompt."""
    failed_tests_str = "\n".join(
        f"- {test['name']}: {test['message']}" for test in failed_tests
    )
    error_messages_str = "\n".join(f"- {msg}" for msg in error_messages)

    return AGENT_FIX_PROMPT.format(
        failed_tests=failed_tests_str,
        error_messages=error_messages_str,
        current_code=current_code,
    )


def format_decision_extraction_prompt(agent_output: str) -> str:
    """Format the decision extraction prompt."""
    return DECISION_EXTRACTION_PROMPT.format(agent_output=agent_output)
