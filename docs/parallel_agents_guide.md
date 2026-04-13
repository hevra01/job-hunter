# Parallel Agents in Claude Code

## What Are Agents?

In Claude Code, **agents** are independent sub-tasks that Claude can spawn to handle work in isolation. Each agent gets its own context window, runs its own tool calls, and returns a single result back to the main conversation.

Think of it like delegating work to a colleague: you brief them on what to do, they go off and do it, and come back with their findings.

## Agent Types

Claude Code has several specialized agent types:

| Type | Purpose | Tools Available |
|------|---------|----------------|
| **Explore** | Fast codebase exploration — find files, search code, answer questions about the repo | Read, Grep, Glob, Bash (read-only) |
| **Plan** | Design implementation strategies — analyze requirements, identify files to change, consider trade-offs | Read, Grep, Glob, Bash (read-only) |
| **general-purpose** | Multi-step tasks — research, code search, web fetches, complex investigations | All tools except Edit/Write |

## How Parallel Agents Work

When Claude needs to investigate multiple **independent** questions, it can launch several agents in a single message. These agents run **concurrently** — they don't wait for each other.

### Sequential (one at a time)
```
User: "Understand how the scrapers and the AI modules work"

Claude:
  1. Launch Agent → explore scrapers/     (waits for result)
  2. Launch Agent → explore ai/           (waits for result)
  3. Synthesize findings
```
Total time: Agent1 time + Agent2 time

### Parallel (simultaneous)
```
User: "Understand how the scrapers and the AI modules work"

Claude:
  1. Launch Agent → explore scrapers/  }
     Launch Agent → explore ai/        }  (both run at the same time)
  2. Synthesize findings
```
Total time: max(Agent1 time, Agent2 time)

## When to Use Parallel Agents

**Good candidates for parallel execution:**

- Exploring different areas of a codebase simultaneously
- Researching multiple independent questions
- Checking several external resources at once
- Comparing different files or patterns across the repo

**Real example from this project** — when planning the interview prep feature, Claude launched 3 Explore agents in parallel:

1. **Agent 1**: Read `.claude/settings.json`, `models.py`, `base.html`, `dashboard.html` — understanding project structure and UI patterns
2. **Agent 2**: Fetch and analyze the GitHub repo `liquidslr/interview-company-wise-problems` — understanding the data source
3. **Agent 3**: Read `scrapers/base.py`, `ai/scorer.py`, `ai/cover_letter.py`, `main.py` — understanding existing code patterns to reuse

All three ran at the same time. Each came back with focused findings. Claude then combined them to write a complete implementation plan.

**Do NOT parallelize when:**

- Agent B needs Agent A's output (e.g., "find the file" then "modify it")
- You need to make sequential changes to the same file
- The second task depends on what the first task discovers

## How to Trigger Parallel Agents

You don't need to do anything special. Parallel agents are a built-in Claude Code capability. When you give Claude a task that involves multiple independent investigations, it will automatically decide whether to run agents in parallel or sequentially.

You can hint at it by saying things like:
- "Explore both the frontend and backend at the same time"
- "Research these three things in parallel"
- "Check all of these simultaneously"

But Claude will also parallelize on its own when it recognizes independent sub-tasks.

## Key Things to Know

1. **No setup required** — parallel agents work out of the box in Claude Code
2. **Each agent starts fresh** — agents don't share context with each other, only with the main conversation
3. **Results come back to Claude** — you see the synthesized output, not raw agent results
4. **Agents can't edit files** — Explore and Plan agents are read-only; only the main conversation makes changes
5. **Cost vs speed trade-off** — parallel agents use more context but finish faster; Claude uses them when the speed benefit is worth it
6. **Background agents** — agents can also run in the background while Claude continues talking to you, useful for long-running research tasks

## Practical Tips

- For **simple lookups** (finding a specific file or function), Claude uses direct tools like Grep/Glob — no agent needed
- For **broad exploration** (understanding how a whole module works), an Explore agent is ideal
- For **planning complex features**, a Plan agent helps think through architecture before writing code
- When you ask Claude to investigate multiple things, it will naturally parallelize where it makes sense
