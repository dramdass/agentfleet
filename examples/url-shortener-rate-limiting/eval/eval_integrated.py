"""Evaluation script for rate limiter integrated into app.py.

This tests that the rate limiting has been properly added to the URL shortener API.

Usage:
    python eval_integrated.py path/to/app.py
"""

import sys
import json
import time
import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch


def load_app(app_path: str):
    """Load the Flask app from a file path."""
    spec = importlib.util.spec_from_file_location("app_module", app_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load app from {app_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def count_lines(file_path: str) -> int:
    """Count non-empty, non-comment lines in a Python file."""
    lines = Path(file_path).read_text().split("\n")
    code_lines = [
        line
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return len(code_lines)


def run_tests(app_path: str) -> dict:
    """Run all tests against the integrated app."""
    results = {
        "success": True,
        "tests": {},
        "metrics": {},
    }

    try:
        app = load_app(app_path)
        client = app.test_client()
    except Exception as e:
        results["success"] = False
        results["tests"]["import_error"] = {
            "pass": False,
            "category": "correctness",
            "message": f"Failed to load app: {e}",
        }
        return results

    # Test 1: Basic functionality still works (no rate limiting yet)
    try:
        response = client.post("/shorten", json={
            "url": "https://example.com",
            "user_id": "test_user_1"
        })

        if response.status_code != 200:
            raise AssertionError(f"Expected 200, got {response.status_code}")

        data = response.get_json()
        if "short_url" not in data:
            raise AssertionError("Response missing 'short_url'")

        results["tests"]["test_basic_functionality"] = {
            "pass": True,
            "category": "correctness",
            "message": "Basic URL shortening works",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_basic_functionality"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Test 2: Rate limiting is enforced (10/min on /shorten)
    try:
        user_id = "test_user_2"

        # Make 10 requests (should all succeed)
        for i in range(10):
            response = client.post("/shorten", json={
                "url": f"https://example.com/{i}",
                "user_id": user_id
            })
            if response.status_code != 200:
                raise AssertionError(f"Request {i+1}/10 should succeed, got {response.status_code}")

        # 11th request should be rate limited
        response = client.post("/shorten", json={
            "url": "https://example.com/11",
            "user_id": user_id
        })

        if response.status_code != 429:
            raise AssertionError(f"11th request should be rate limited (429), got {response.status_code}")

        results["tests"]["test_rate_limit_enforced"] = {
            "pass": True,
            "category": "correctness",
            "message": "Rate limiting correctly enforces 10 req/min limit",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_rate_limit_enforced"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Test 3: Per-user isolation
    try:
        # User A maxes out their limit
        for i in range(10):
            client.post("/shorten", json={
                "url": f"https://example.com/a{i}",
                "user_id": "user_a"
            })

        # User A should be rate limited
        response_a = client.post("/shorten", json={
            "url": "https://example.com/a_extra",
            "user_id": "user_a"
        })
        if response_a.status_code != 429:
            raise AssertionError("User A should be rate limited")

        # User B should still be allowed
        response_b = client.post("/shorten", json={
            "url": "https://example.com/b1",
            "user_id": "user_b"
        })
        if response_b.status_code != 200:
            raise AssertionError(f"User B should not be rate limited, got {response_b.status_code}")

        results["tests"]["test_per_user_isolation"] = {
            "pass": True,
            "category": "correctness",
            "message": "Rate limiting is per-user (isolated)",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_per_user_isolation"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Test 4: Boundary case (window edge)
    try:
        user_id = "boundary_test_user"

        # This test is tricky - we're checking for the fixed window bug
        # Make 10 requests
        for i in range(10):
            client.post("/shorten", json={
                "url": f"https://example.com/boundary{i}",
                "user_id": user_id
            })

        # Wait briefly
        time.sleep(1.5)

        # Try 10 more requests
        # Sliding window: should deny most/all (still in 60s window)
        # Token bucket: might allow 1-2 (tokens regenerate)
        # Fixed window: incorrectly allows all 10 (new window)
        allowed = 0
        for i in range(10):
            response = client.post("/shorten", json={
                "url": f"https://example.com/boundary2_{i}",
                "user_id": user_id
            })
            if response.status_code == 200:
                allowed += 1

        # If all 10 are allowed, it's the fixed window bug
        if allowed >= 10:
            raise AssertionError(
                f"Boundary bug detected: {allowed}/10 requests allowed after 1.5s, "
                "should deny most/all (still within 60s window)"
            )

        results["tests"]["test_boundary_handling"] = {
            "pass": True,
            "category": "edge_cases",
            "message": f"Boundary handling correct ({allowed}/10 allowed at edge)",
        }
    except AssertionError as e:
        results["success"] = False
        results["tests"]["test_boundary_handling"] = {
            "pass": False,
            "category": "edge_cases",
            "message": str(e),
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_boundary_handling"] = {
            "pass": False,
            "category": "edge_cases",
            "message": f"Test error: {e}",
        }

    # Test 5: Integration quality (code organization)
    try:
        # Check that rate limiter is defined in the file
        source = Path(app_path).read_text()

        if "allow_request" not in source:
            raise AssertionError("Rate limiter not properly integrated (missing allow_request method)")

        if "429" not in source:
            raise AssertionError("Rate limit error response (429) not implemented")

        # Check that shorten endpoint calls allow_request
        # Find the create_short_url function
        shorten_start = source.find("def create_short_url")
        shorten_end = source.find("\n@app.route", shorten_start + 1)
        if shorten_end == -1:
            shorten_end = source.find("\ndef ", shorten_start + 1)
        if shorten_end == -1:
            shorten_end = len(source)

        shorten_func = source[shorten_start:shorten_end]
        if "allow_request" not in shorten_func:
            raise AssertionError("/shorten endpoint does not call allow_request")

        results["tests"]["test_integration_quality"] = {
            "pass": True,
            "category": "correctness",
            "message": "Rate limiter properly integrated into app",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_integration_quality"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Compute metrics
    tests = results["tests"]
    correctness_tests = [t for t in tests.values() if t["category"] == "correctness"]
    edge_case_tests = [t for t in tests.values() if t["category"] == "edge_cases"]

    correctness_score = (
        sum(1 for t in correctness_tests if t["pass"]) / len(correctness_tests)
        if correctness_tests
        else 0.0
    )

    edge_case_score = (
        sum(1 for t in edge_case_tests if t["pass"]) / len(edge_case_tests)
        if edge_case_tests
        else 1.0
    )

    # Simplicity: based on lines added (fewer is better)
    # Baseline app.py has ~70 lines, good implementations add 30-50 lines
    lines = count_lines(app_path)
    lines_added = lines - 70
    simplicity_score = max(0.0, min(1.0, (100 - lines_added) / 100))

    # Performance: placeholder
    performance_score = 0.8

    results["metrics"] = {
        "correctness_score": correctness_score,
        "simplicity_score": simplicity_score,
        "performance_score": performance_score,
        "lines_of_code": lines,
        "lines_added": lines_added,
        "edge_case_score": edge_case_score,
    }

    return results


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python eval_integrated.py path/to/app.py", file=sys.stderr)
        sys.exit(1)

    app_path = sys.argv[1]
    results = run_tests(app_path)

    # Print JSON results
    print(json.dumps(results, indent=2))

    # Exit with appropriate code
    sys.exit(0 if results["success"] else 1)
