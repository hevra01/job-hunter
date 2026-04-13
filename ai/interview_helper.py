"""
AI-powered interview preparation assistant.

Uses the Claude Code CLI (`claude -p`) to provide hints, explain approaches,
and review user solutions for LeetCode problems. Falls back to a basic
text response if the CLI is unavailable.
"""
import logging
import subprocess

logger = logging.getLogger(__name__)

CLAUDE_CLI = "/home/hevra/.npm-global/bin/claude"


def get_ai_response(problem_title, problem_url, difficulty, topics, hint_type, user_solution=None):
    """Get AI assistance for an interview problem.

    hint_type: "hint" | "approach" | "review"
    """
    prompt = _build_prompt(problem_title, difficulty, topics, hint_type, user_solution)
    try:
        return _call_claude(prompt)
    except Exception as e:
        logger.warning("Claude CLI interview helper failed: %s", e)
        return _fallback_response(problem_title, problem_url, hint_type)


def _build_prompt(title, difficulty, topics, hint_type, user_solution=None):
    """Build the prompt based on hint type."""
    base = f"LeetCode Problem: {title}\nDifficulty: {difficulty}\nTopics: {topics}\n\n"

    if hint_type == "hint":
        return base + (
            "Give me 2-3 progressive hints for solving this problem, "
            "starting from a gentle nudge and getting more specific. "
            "Do NOT give the full solution or code. "
            "Format each hint as a numbered step."
        )
    elif hint_type == "approach":
        return base + (
            "Explain the optimal solution approach for this problem. Cover:\n"
            "1. Key insight or trick\n"
            "2. Which data structure(s) to use and why\n"
            "3. Step-by-step algorithm\n"
            "4. Time and space complexity\n"
            "5. A brief Python code solution\n"
            "Be clear and concise."
        )
    elif hint_type == "review":
        return base + (
            f"Review my solution for this problem:\n\n```\n{user_solution or 'No solution provided'}\n```\n\n"
            "Provide:\n"
            "1. Correctness assessment — does it handle all cases?\n"
            "2. Time and space complexity analysis\n"
            "3. Potential edge cases it might miss\n"
            "4. Suggestions for improvement\n"
            "Be constructive and specific."
        )
    else:
        return base + "Explain this problem and how to approach it."


def _call_claude(prompt):
    """Call Claude CLI in print mode."""
    result = subprocess.run(
        [CLAUDE_CLI, "-p", "--model", "sonnet", "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI exit {result.returncode}: {result.stderr[:200]}")

    text = result.stdout.strip()
    if not text:
        raise RuntimeError("Claude CLI returned empty output")
    return text


def _fallback_response(title, url, hint_type):
    """Fallback when Claude CLI is unavailable."""
    if hint_type == "hint":
        return (
            f"AI assistant is currently unavailable.\n\n"
            f"Tip: Try breaking down '{title}' into smaller sub-problems. "
            f"Think about what data structure would give you the best time complexity.\n\n"
            f"Open on LeetCode: {url}"
        )
    elif hint_type == "approach":
        return (
            f"AI assistant is currently unavailable.\n\n"
            f"Check the LeetCode discussion tab for community solutions: {url}\n"
            f"Look for solutions tagged with: {title}"
        )
    else:
        return (
            f"AI assistant is currently unavailable.\n\n"
            f"Try running your solution against the LeetCode test cases: {url}"
        )
