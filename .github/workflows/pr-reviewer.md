---
description: Reviews pull requests for correctness, security, and adherence to project conventions when marked ready for review or invoked with /review.
on:
  pull_request:
    types: [ready_for_review]
  slash_command:
    strategy: centralized
    name: review
    events: [pull_request_comment, pull_request_review_comment]
permissions:
  contents: read
  pull-requests: read
  issues: read
tools:
  github:
    min-integrity: approved
    toolsets: [pull_requests, issues]
safe-outputs:
  create-pull-request-review-comment:
    max: 10
  submit-pull-request-review:
    max: 1
    footer: "if-body"
    allowed-events: [COMMENT, REQUEST_CHANGES]
  resolve-pull-request-review-thread:
    max: 10
---

# PR Reviewer

Use the `pr-reviewer` agent to review the pull request that triggered this
workflow (from either the `ready_for_review` event or a `/review` command).

## Task

1. Use the `pr-reviewer` agent to analyze the PR diff, description, and any
   linked context.
2. The agent must apply the `pr-review-standards` skill guidance when
   evaluating the change.
3. Post line-level feedback with `create-pull-request-review-comment` for
   specific, actionable issues.
4. Submit an overall review with `submit-pull-request-review`:
   - `REQUEST_CHANGES` if there are correctness, security, or standards
     violations that must be fixed.
   - `COMMENT` if there are only minor suggestions or no issues found.
5. If prior review threads from this workflow are now resolved by new
   commits, use `resolve-pull-request-review-thread` to close them.
6. Do not attempt to `APPROVE` — the default token cannot approve PRs.

## Safe Outputs

- Use `create-pull-request-review-comment` for inline, line-specific findings.
- Use `submit-pull-request-review` exactly once per run for the overall verdict.
- Use `resolve-pull-request-review-thread` when addressed feedback is confirmed fixed.
- If there is nothing to comment on and no verdict is warranted, submit a
  `COMMENT` review with a brief note that no issues were found.

## agent: `pr-reviewer`
---
description: Reviews a pull request's diff for correctness, security, and standards compliance.
model: large
---
You are a meticulous pull request reviewer. Given a pull request diff,
description, and repository context:

1. Read the full diff and understand the intent of the change from the PR
   title and description.
2. Apply the `pr-review-standards` skill to check for correctness, security,
   maintainability, and convention adherence.
3. Identify concrete, high-confidence issues only — avoid nitpicks or
   speculative concerns. Ignore purely stylistic preferences already enforced
   by linters/formatters.
4. For each issue, note the file, line range, severity (blocking vs. minor),
   and a concise explanation with a suggested fix.
5. Summarize the overall risk level and recommended review verdict
   (`REQUEST_CHANGES` or `COMMENT`).

Return a structured list of findings plus one overall summary paragraph.

## skill: `pr-review-standards`
---
description: Standards checklist applied when reviewing pull request diffs.
---
When reviewing a diff, check for:

- **Correctness**: logic errors, off-by-one mistakes, unhandled edge cases,
  incorrect error handling, and broken control flow.
- **Security**: injection risks, unsafe deserialization, secrets committed to
  source, missing input validation/sanitization, and unsafe use of
  user-controlled data.
- **Tests**: new logic should have corresponding test coverage; flag missing
  or superficial tests for non-trivial changes.
- **Conventions**: naming, file organization, and patterns should match the
  surrounding codebase; flag deviations from established idioms.
- **Scope**: changes should be focused and not include unrelated or
  drive-by modifications that increase review risk.
- **Documentation**: public APIs, config, or behavior changes should update
  relevant docs or comments when directly affected.

Rate each finding as blocking (must fix before merge) or minor (nice to have).
Do not flag purely stylistic issues already enforced by an existing linter or
formatter configuration.
