CLAUDE.md
Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

5. Language
All reasoning and judgment are done in English internally.
All responses are written in Korean.

6. Scope Clarification (MANDATORY)
Never start implementation without confirming scope on ambiguous tasks.

Before starting any task that involves 3+ files, architectural decisions, new dependencies, or unclear requirements:
- Ask at least one clarifying question.
- Do not silently pick an interpretation — present options.
- After 3 failed attempts on the same approach, stop and ask.

7. Plan Mode
Use Plan Mode (Shift+Tab in IDE) before implementing complex changes.

Triggers that require a plan:
- Modifying 3+ files simultaneously
- Adding a new dependency or replacing an existing one
- Changing a public API or data contract
- Any database schema change

8. Extended Guidelines
Detailed rules live in .claude/rules/ — they extend but do not override the principles above:
- boundaries.md  — what to do autonomously vs. ask first vs. never
- git-workflow.md — commit conventions for this project
- security.md     — pre-commit security checklist

9. Work Division & Workflow Routing
Scale rigor to task complexity. Two distinct actors with different mandates:

- Work division: the deployed Telegram bot/worker agents NEVER modify code. Their tools are sandboxed to research, documentation, and `prompts/output/` artifacts (write_file → `prompts/output/` only, bash → read-only allowlist, vault_save → `vault/` only). Applying code changes is the job of the local coding agent (Claude Code), not the bot. `/commit`·`/push` stay human-gated and only commit docs/output/vault changes.
- Routing by complexity (for the LOCAL coding agent):
  - Light requests (small edits, single-file fixes, questions, explanations) → follow the principles in this CLAUDE.md and proceed proportionally. No heavyweight process.
  - Substantial changes (new features, 3+ files, public API / data-contract / schema changes) → treat the 6-stage workflow in `prompts/01~06.md` (analyze → research → design → implement → review → test) as the standard, including its human-approval gates at stages 03 and 05. Scale down for smaller work.
