---
name: Daily Report Status
on:
  schedule: daily
  workflow_dispatch:
permissions:
  contents: read
  issues: read
  pull-requests: read
  copilot-requests: write
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
safe-outputs:
  create-issue:
---

# Daily Report Status

Generate an activity report in a new issue. Review the repository activity for the
last 24 full hours ending at workflow start (UTC), summarize the key updates in
GitHub-flavored Markdown, and use the configured `create-issue` safe output to
publish the report. Call `noop` if there were no qualifying updates.
