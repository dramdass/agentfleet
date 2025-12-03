"""Example evaluation script for rate limiter implementations.

This is an example of what the AgentFleet supervisor agent would generate.
It can be run manually against reference implementations for testing.

Usage:
    python eval_example.py path/to/solution.py
"""

import sys
import json
import time
import importlib.util
from pathlib import Path


def load_solution(solution_path: str):
    """Load the solution module from a file path."""
    spec = importlib.util.spec_from_file_location("solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load solution from {solution_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def count_lines(file_path: str) -> int:
    """Count non-empty, non-comment lines in a Python file."""
    lines = Path(file_path).read_text().split("\n")
    code_lines = [
        line
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return len(code_lines)


def run_tests(solution_path: str) -> dict:
    """Run all tests against the solution."""
    results = {
        "success": True,
        "tests": {},
        "metrics": {},
    }

    try:
        solution = load_solution(solution_path)
        RateLimiter = solution.RateLimiter
    except Exception as e:
        results["success"] = False
        results["tests"]["import_error"] = {
            "pass": False,
            "category": "correctness",
            "message": f"Failed to import solution: {e}",
        }
        return results

    # Test 1: Basic functionality
    try:
        limiter = RateLimiter(limit=5, window=60)
        user_id = "user1"

        # Should allow first 5 requests
        for i in range(5):
            if not limiter.allow_request(user_id):
                raise AssertionError(f"Request {i+1}/5 should be allowed")

        # 6th request should be denied
        if limiter.allow_request(user_id):
            raise AssertionError("6th request should be rate limited")

        results["tests"]["test_basic"] = {
            "pass": True,
            "category": "correctness",
            "message": "Basic functionality works",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_basic"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Test 2: Per-user isolation
    try:
        limiter = RateLimiter(limit=2, window=60)

        # User1 makes 2 requests
        limiter.allow_request("user1")
        limiter.allow_request("user1")

        # User1's 3rd should be denied
        if limiter.allow_request("user1"):
            raise AssertionError("User1's 3rd request should be denied")

        # User2's first should be allowed (separate limit)
        if not limiter.allow_request("user2"):
            raise AssertionError("User2's first request should be allowed")

        results["tests"]["test_per_user"] = {
            "pass": True,
            "category": "correctness",
            "message": "Per-user isolation works",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_per_user"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Test 3: Reset functionality
    try:
        limiter = RateLimiter(limit=2, window=60)
        user_id = "user1"

        # Use up limit
        limiter.allow_request(user_id)
        limiter.allow_request(user_id)

        # Should be denied
        if limiter.allow_request(user_id):
            raise AssertionError("Should be rate limited before reset")

        # Reset and try again
        limiter.reset(user_id)

        # Should be allowed after reset
        if not limiter.allow_request(user_id):
            raise AssertionError("Should be allowed after reset")

        results["tests"]["test_reset"] = {
            "pass": True,
            "category": "correctness",
            "message": "Reset functionality works",
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_reset"] = {
            "pass": False,
            "category": "correctness",
            "message": str(e),
        }

    # Test 4: Boundary case (critical for catching fixed window bug!)
    try:
        limiter = RateLimiter(limit=5, window=2)  # 5 requests per 2 seconds
        user_id = "user1"

        # Make 5 requests
        for _ in range(5):
            limiter.allow_request(user_id)

        # Sleep 1.5 seconds (still within window)
        time.sleep(1.5)

        # Try 5 more requests - these should mostly be denied
        # because we're still within the 2-second window
        allowed_count = sum(1 for _ in range(5) if limiter.allow_request(user_id))

        # For sliding window: should allow 0 (we're at 1.5s, all 5 previous are still in window)
        # For token bucket: might allow 1-2 (tokens regenerate continuously)
        # For fixed window: will incorrectly allow all 5 (new window started)

        if allowed_count >= 5:
            # This is the fixed window bug!
            raise AssertionError(
                f"Boundary bug detected: allowed {allowed_count}/5 requests "
                "at window edge, should deny most/all"
            )

        results["tests"]["test_boundary"] = {
            "pass": True,
            "category": "edge_cases",
            "message": f"Boundary handling correct (allowed {allowed_count}/5 at edge)",
        }
    except AssertionError as e:
        results["success"] = False
        results["tests"]["test_boundary"] = {
            "pass": False,
            "category": "edge_cases",
            "message": str(e),
        }
    except Exception as e:
        results["success"] = False
        results["tests"]["test_boundary"] = {
            "pass": False,
            "category": "edge_cases",
            "message": f"Test error: {e}",
        }

    # Test 5: Thread safety (basic smoke test)
    try:
        import threading

        limiter = RateLimiter(limit=100, window=60)
        user_id = "user1"
        errors = []

        def make_requests():
            try:
                for _ in range(50):
                    limiter.allow_request(user_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=make_requests) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            raise AssertionError(f"Thread safety errors: {errors}")

        results["tests"]["test_thread_safety"] = {
            "pass": True,
            "category": "performance",
            "message": "Thread safety smoke test passed",
        }
    except Exception as e:
        # Don't fail the whole suite on thread safety
        results["tests"]["test_thread_safety"] = {
            "pass": False,
            "category": "performance",
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

    # Simplicity: based on lines of code (fewer is better)
    lines = count_lines(solution_path)
    simplicity_score = max(0.0, min(1.0, (100 - lines) / 100))

    # Performance: placeholder (would measure actual latency in real eval)
    performance_score = 0.8

    results["metrics"] = {
        "correctness_score": correctness_score,
        "simplicity_score": simplicity_score,
        "performance_score": performance_score,
        "lines_of_code": lines,
        "edge_case_score": edge_case_score,
    }

    return results


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python eval_example.py path/to/solution.py", file=sys.stderr)
        sys.exit(1)

    solution_path = sys.argv[1]
    results = run_tests(solution_path)

    # Print JSON results
    print(json.dumps(results, indent=2))

    # Exit with appropriate code
    sys.exit(0 if results["success"] else 1)
