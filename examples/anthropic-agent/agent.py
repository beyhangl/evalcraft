"""Code review agent — a multi-turn Claude-powered code reviewer.

The agent reviews pull request diffs by:
1. Fetching the diff content
2. Running static analysis (lint check, complexity check)
3. Iterating with Claude through multiple turns to produce a structured review

Multi-turn design: Claude first reads the diff and decides which checks to run,
then synthesizes all findings into a final structured review comment.

This file contains agent logic only. evalcraft instrumentation lives in tests/.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Fake tools (replace with real GitHub API / linting tools in production)
# ---------------------------------------------------------------------------

def fetch_pr_diff(repo: str, pr_number: int) -> dict:
    """Fetch the diff for a pull request."""
    # Simulated diff — in production: call GitHub REST API
    diffs = {
        101: {
            "title": "Add user authentication middleware",
            "files_changed": 3,
            "additions": 87,
            "deletions": 12,
            "diff": """
+++ b/middleware/auth.py
@@ -0,0 +1,45 @@
+import jwt
+import os
+from functools import wraps
+from flask import request, jsonify
+
+SECRET_KEY = os.environ.get('JWT_SECRET', 'hardcoded-fallback-secret')
+
+def require_auth(f):
+    @wraps(f)
+    def decorated(*args, **kwargs):
+        token = request.headers.get('Authorization', '').replace('Bearer ', '')
+        if not token:
+            return jsonify({'error': 'Missing token'}), 401
+        try:
+            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
+            request.user_id = payload['sub']
+        except jwt.ExpiredSignatureError:
+            return jsonify({'error': 'Token expired'}), 401
+        except jwt.InvalidTokenError:
+            return jsonify({'error': 'Invalid token'}), 401
+        return f(*args, **kwargs)
+    return decorated
""",
        },
        102: {
            "title": "Refactor database connection pooling",
            "files_changed": 2,
            "additions": 34,
            "deletions": 58,
            "diff": """
+++ b/db/pool.py
@@ -12,6 +12,18 @@
-MAX_CONNECTIONS = 100
+MAX_CONNECTIONS = int(os.environ.get('DB_MAX_CONNECTIONS', '10'))
+MIN_CONNECTIONS = int(os.environ.get('DB_MIN_CONNECTIONS', '2'))
+
+def get_pool():
+    return ConnectionPool(
+        min_size=MIN_CONNECTIONS,
+        max_size=MAX_CONNECTIONS,
+        timeout=30,
+    )
""",
        },
    }
    return diffs.get(pr_number, {"error": f"PR #{pr_number} not found in {repo}"})


def run_lint_check(code_snippet: str, language: str = "python") -> dict:
    """Run static analysis on a code snippet."""
    issues = []

    # Simulated linting rules
    if "hardcoded" in code_snippet.lower() or "'hardcoded-fallback-secret'" in code_snippet:
        issues.append({
            "rule": "S2068",
            "severity": "CRITICAL",
            "message": "Hardcoded secret/password detected",
            "line": 6,
        })

    if "os.environ.get" in code_snippet and "fallback" not in code_snippet.lower():
        pass  # environment vars without fallback — would warn in real linter

    if len(re.findall(r"def \w+", code_snippet)) > 10:
        issues.append({
            "rule": "C901",
            "severity": "WARNING",
            "message": "Module has too many functions",
        })

    return {
        "language": language,
        "issues": issues,
        "issue_count": len(issues),
        "passed": len([i for i in issues if i["severity"] == "CRITICAL"]) == 0,
    }


def check_test_coverage(repo: str, pr_number: int) -> dict:
    """Check if the PR includes tests."""
    coverage_data = {
        101: {
            "has_tests": False,
            "test_files_changed": 0,
            "coverage_delta": -2.3,
            "warning": "No test files modified in this PR",
        },
        102: {
            "has_tests": True,
            "test_files_changed": 1,
            "coverage_delta": +1.8,
            "warning": None,
        },
    }
    return coverage_data.get(pr_number, {"has_tests": False, "test_files_changed": 0})


# ---------------------------------------------------------------------------
# Tool schemas for Claude
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "fetch_pr_diff",
        "description": "Fetch the diff and metadata for a pull request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository name (owner/repo)"},
                "pr_number": {"type": "integer", "description": "Pull request number"},
            },
            "required": ["repo", "pr_number"],
        },
    },
    {
        "name": "run_lint_check",
        "description": "Run static analysis / linting on a code snippet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code_snippet": {"type": "string", "description": "Code to analyze"},
                "language": {"type": "string", "description": "Programming language", "default": "python"},
            },
            "required": ["code_snippet"],
        },
    },
    {
        "name": "check_test_coverage",
        "description": "Check whether the PR includes test changes and coverage impact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "pr_number": {"type": "integer"},
            },
            "required": ["repo", "pr_number"],
        },
    },
]

TOOL_MAP: dict[str, Any] = {
    "fetch_pr_diff": fetch_pr_diff,
    "run_lint_check": run_lint_check,
    "check_test_coverage": check_test_coverage,
}

SYSTEM_PROMPT = """You are an expert code reviewer. Your job is to review pull requests \
thoroughly and produce a structured, actionable review.

Always:
1. Fetch the PR diff first
2. Run a lint check on the added code
3. Check test coverage
4. Produce a structured review with sections: Summary, Issues Found, Recommendations, Verdict

Be specific and reference line numbers where relevant. Use a professional but collegial tone."""


# ---------------------------------------------------------------------------
# Multi-turn agent loop
# ---------------------------------------------------------------------------

def run_code_review_agent(client: Any, repo: str, pr_number: int) -> str:
    """Run the code review agent for a PR.

    Args:
        client: An anthropic.Anthropic() client instance.
        repo: Repository name (e.g. "myorg/myrepo").
        pr_number: Pull request number.

    Returns:
        The agent's structured review as a string.
    """
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Please review pull request #{pr_number} in the {repo} repository. "
                "Provide a thorough code review with specific findings and recommendations."
            ),
        }
    ]

    for _turn in range(6):  # safety cap on turns
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )

        if response.stop_reason == "end_turn":
            # Extract the final text response
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            # Append assistant's response (with tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    fn = TOOL_MAP.get(block.name)
                    result = fn(**block.input) if fn else {"error": f"Unknown tool: {block.name}"}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            messages.append({"role": "user", "content": tool_results})

    return "Review could not be completed — maximum turns reached."
