# Example: Adding Rate Limiting to a URL Shortener

This example demonstrates using AgentFleet to add rate limiting to an existing Flask application.

## The Challenge

Starting with a basic URL shortener API ([flask-url-shortener](https://github.com/dramdass/flask-url-shortener)), we want to add rate limiting to prevent abuse:
- `/shorten` endpoint: 10 requests per minute per user
- `/<short_code>` redirect: 100 requests per minute per user

## Three Approaches Compared

AgentFleet will run three agents in parallel, each implementing a different rate limiting strategy:

### 1. Token Bucket
Accumulates tokens at a fixed rate. Each request consumes one token.
- **Pros:** Smooth rate limiting, allows controlled bursts
- **Cons:** More complex state management

### 2. Sliding Window
Tracks exact timestamps of requests in a rolling window.
- **Pros:** Most accurate, handles boundary cases correctly
- **Cons:** Higher memory usage for high-traffic scenarios

### 3. Fixed Window
Divides time into fixed intervals, resets counters at boundaries.
- **Pros:** Very simple, memory efficient
- **Cons:** Boundary bug—allows 2x requests at window edges!

## Running This Example

### Prerequisites
```bash
# Clone the URL shortener app
git clone https://github.com/dramdass/flask-url-shortener.git

# Set your Anthropic API key
export ANTHROPIC_API_KEY=your_key_here
```

### Run the Tournament

```bash
agentfleet \
  "Add rate limiting to app.py: 10 req/min on /shorten, 100 req/min on redirects, per-user. Use the {approach} approach." \
  "Token bucket" "Sliding window" "Fixed window" \
  --repo flask-url-shortener \
  --work-dir ./work
```

The `--repo` flag points AgentFleet to the flask-url-shortener git repository. Each agent gets an independent git worktree with its own branch:
- `agent/token-bucket`
- `agent/sliding-window`
- `agent/fixed-window`

After the tournament, you can inspect each agent's implementation:
```bash
cd flask-url-shortener
git worktree list          # See all worktrees
git diff agent/sliding-window agent/token-bucket  # Compare approaches
```

The worktrees remain after the tournament so you can review, test, or merge the winning approach.

### What Happens

1. **Supervisor Planning** - Generates evaluation criteria based on the task
2. **Parallel Execution** - Three agents simultaneously modify `app.py` with different approaches
3. **Evaluation** - Each implementation tested against the eval script
4. **Ranking** - Results scored by correctness, simplicity, performance

### Expected Results

```
🥇 WINNER: Sliding window (94/100)
✅ All tests passed
📊 Correctness: 1.0 | Simplicity: 0.88 | Performance: 0.8
🔍 Decisions: 3 recorded

🥈 Token bucket (87/100)
✅ All tests passed
📊 Correctness: 1.0 | Simplicity: 0.75 | Performance: 0.8

🥉 Fixed window (45/100)
❌ Failed boundary test
📊 Correctness: 0.6 | Simplicity: 0.9 | Performance: 0.8
```

## Reference Implementations

The `reference/` directory contains example implementations for study:

### Standalone Rate Limiters
- `token_bucket.py` - Token bucket implementation
- `sliding_window.py` - Sliding window implementation
- `fixed_window.py` - Fixed window implementation (with boundary bug)

### Integrated Examples
- `app_with_token_bucket.py` - Complete app with token bucket
- `app_with_sliding_window.py` - Complete app with sliding window
- `app_with_fixed_window.py` - Complete app with fixed window

**Note:** Agents don't see these! They start with the unmodified `app.py` and add rate limiting from scratch.

## Testing Reference Implementations

```bash
# Install dependencies
cd flask-url-shortener
python3 -m venv venv
source venv/bin/activate
pip install flask

# Test standalone rate limiters
cd ../agentfleet/examples/url-shortener-rate-limiting
python eval/eval_example.py reference/sliding_window.py

# Test integrated apps
python eval/eval_integrated.py reference/app_with_sliding_window.py
```

## Evaluation Scripts

### `eval/eval_example.py`
Tests standalone rate limiter classes with these checks:
- Basic functionality (allow N requests, deny N+1)
- Per-user isolation
- Reset functionality
- **Boundary case** (detects fixed window bug)
- Thread safety

### `eval/eval_integrated.py`
Tests rate limiting integrated into the Flask app:
- Basic URL shortening still works
- Rate limiting enforced on endpoints
- Per-user isolation
- Boundary handling
- Integration quality (proper code organization)

## The Boundary Bug

Fixed window rate limiters have a classic problem:

```
Limit: 10 requests/minute

Window 1: [00:00 - 01:00]
Window 2: [01:00 - 02:00]

Timeline:
00:59 → Make 10 requests ✅ (allowed, window 1)
01:01 → Make 10 requests ✅ (allowed, window 2)

Result: 20 requests in 2 seconds!
```

The sliding window approach avoids this by maintaining a rolling 60-second window based on exact timestamps.

## What This Example Demonstrates

1. **Real-world integration** - Agents modify existing code, not isolated modules
2. **Blind evaluation** - Supervisor designs tests before seeing implementations
3. **Decision trails** - Each agent records interpretive choices
4. **Bug detection** - Boundary bug in fixed window caught automatically
5. **Parallel exploration** - All approaches run simultaneously

## Directory Structure

```
examples/url-shortener-rate-limiting/
├── README.md                          # This file
├── reference/                         # Reference implementations
│   ├── token_bucket.py
│   ├── sliding_window.py
│   ├── fixed_window.py
│   ├── app_with_token_bucket.py
│   ├── app_with_sliding_window.py
│   └── app_with_fixed_window.py
└── eval/                              # Evaluation scripts
    ├── eval_example.py                # Tests standalone rate limiters
    └── eval_integrated.py             # Tests integrated apps
```
