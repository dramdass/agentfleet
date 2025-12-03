"""Supervisor agent that generates evaluation plans."""

import json
import os
from typing import Any

from anthropic import Anthropic

from agentfleet.models import Plan
from agentfleet.prompts import format_supervisor_prompt


async def generate_plan(task: str, approaches: list[str]) -> Plan:
    """Generate an evaluation plan using the supervisor agent.

    The supervisor designs evaluation criteria BEFORE seeing any implementation,
    ensuring fair, unbiased comparison.

    Args:
        task: The programming task description
        approaches: List of approach names to compare (e.g., ["Token bucket", "Sliding window"])

    Returns:
        Plan object with resolved task, tests, metrics, weights, and eval script

    Raises:
        ValueError: If plan generation fails or returns invalid data
        RuntimeError: If API call fails
    """
    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    # Get model (with default)
    model = os.getenv("AGENTFLEET_MODEL", "claude-sonnet-4-20250514")

    # Create client
    client = Anthropic(api_key=api_key)

    # Format prompt
    prompt = format_supervisor_prompt(task, approaches)

    # Call Claude
    try:
        response = client.messages.create(
            model=model,
            max_tokens=int(os.getenv("AGENTFLEET_MAX_TOKENS", "8192")),
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract response text
        response_text = response.content[0].text

        # Parse JSON from response
        plan_data = _extract_json_from_response(response_text)

        # Validate and create Plan
        return _create_plan_from_data(plan_data)

    except Exception as e:
        raise RuntimeError(f"Failed to generate plan: {e}") from e


def _extract_json_from_response(response: str) -> dict[str, Any]:
    """Extract JSON from Claude's response.

    Claude might wrap JSON in markdown code blocks or include explanatory text.
    This function extracts the JSON object.

    Args:
        response: Raw response text from Claude

    Returns:
        Parsed JSON as dictionary

    Raises:
        ValueError: If JSON cannot be found or parsed
    """
    # Try to find JSON in code blocks
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        json_str = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        json_str = response[start:end].strip()
    else:
        # Try to find JSON by looking for { } brackets
        start = response.find("{")
        end = response.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in response")
        json_str = response[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}\n\nJSON string:\n{json_str}") from e


def _create_plan_from_data(data: dict[str, Any]) -> Plan:
    """Create a Plan object from parsed JSON data.

    Args:
        data: Dictionary containing plan fields

    Returns:
        Validated Plan object

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Validate required fields
    required_fields = [
        "resolved_task",
        "interface_contract",
        "tests",
        "metrics",
        "weights",
        "eval_script",
    ]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(f"Missing required fields in plan: {missing}")

    # Validate tests structure
    if not isinstance(data["tests"], list) or len(data["tests"]) < 3:
        raise ValueError("Plan must include at least 3 tests")

    for test in data["tests"]:
        if not all(k in test for k in ["name", "category"]):
            raise ValueError(f"Test missing required fields: {test}")
        if test["category"] not in ["correctness", "edge_cases", "performance"]:
            raise ValueError(f"Invalid test category: {test['category']}")

    # Validate metrics
    if not isinstance(data["metrics"], list) or len(data["metrics"]) < 3:
        raise ValueError("Plan must include at least 3 metrics")

    # Validate weights
    if not isinstance(data["weights"], dict):
        raise ValueError("Weights must be a dictionary")

    # Ensure weights have at least correctness, simplicity, performance
    required_categories = ["correctness", "simplicity", "performance"]
    for cat in required_categories:
        if cat not in data["weights"]:
            raise ValueError(f"Weights missing required category: {cat}")

    # Validate weights sum to 100
    total_weight = sum(data["weights"].values())
    if abs(total_weight - 100.0) > 0.01:
        raise ValueError(f"Weights must sum to 100, got {total_weight}")

    # Create Plan
    return Plan(
        resolved_task=data["resolved_task"],
        interface_contract=data["interface_contract"],
        tests=data["tests"],
        metrics=data["metrics"],
        weights=data["weights"],
        eval_script=data["eval_script"],
    )


def validate_eval_script(eval_script: str) -> bool:
    """Validate that an eval script has the required structure.

    Args:
        eval_script: Python source code for evaluation script

    Returns:
        True if script appears valid

    Raises:
        ValueError: If script is missing required elements
    """
    # Check for required imports/elements
    required_elements = [
        "import sys",
        "import json",
        "if __name__",
        'sys.argv[1]',
        "print(json.dumps(",
        "sys.exit(",
    ]

    missing = [elem for elem in required_elements if elem not in eval_script]
    if missing:
        raise ValueError(f"Eval script missing required elements: {missing}")

    return True
