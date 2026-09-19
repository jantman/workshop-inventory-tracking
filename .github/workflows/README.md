# GitHub Actions Workflows

This directory contains automated workflows for the Workshop Inventory Tracking project.

## Workflows

### 🧪 `test.yml` - Main Test Suite
**Triggers:** Push to `main`/`develop`, Pull Requests
**Purpose:** Comprehensive testing and coverage reporting

**Jobs:**
- **Unit Tests**: Python 3.13 testing
- **Coverage**: Code coverage analysis with PR comments
- **E2E Tests**: End-to-end browser testing with Playwright
- **Docker Build**: Builds the image, pushes it to GHCR as `ci-<commit-sha>`, and smoke-tests `/health`
- **Test Summary**: Consolidated results and artifact management

### 🚀 `release.yml` - Release and Publish
**Triggers:** Push to `main`, manual dispatch
**Purpose:** Cut a SemVer release when the version is bumped

**Jobs:**
- **Check Version**: Compares `version` in `pyproject.toml` to the latest GitHub release
- **Create Release**: If the version is higher, pushes `ghcr.io/jantman/workshop-inventory-tracking:<version>` and `:latest`, then creates a `v<version>` GitHub release

Merges to `main` that do not bump the version are a no-op. See
[Versioning and Releases](../../docs/deployment-guide.md#versioning-and-releases).

> The Docker build configuration is duplicated between `test.yml` and
> `release.yml`; keep the two in sync when changing build arguments or labels.

**Artifacts on Failure:**
- `test-debug-output/` - E2E test failure diagnostics (screenshots, HTML dumps, console logs)
- `test-results/` - Playwright test results
- `.pytest_cache/` - Pytest cache and logs
- `coverage-reports` - HTML and XML coverage reports

### 🤖 `claude-pr-review.yml` and `claude-mention.yml` - Claude Code

These two look redundant and are not. **Do not delete one as a duplicate of the
other** — that happened in `1f5e2ae` and silently broke `@claude` for a day.

| | `claude-pr-review.yml` | `claude-mention.yml` |
|---|---|---|
| **Triggers** | `pull_request` | `issue_comment`, `issues`, `pull_request_review*` + `@claude` |
| **Asked for?** | No — reviews every PR unprompted | Yes — only when you write `@claude` |
| **Action mode** | agent (a `prompt` is supplied) | tag (no `prompt`) |
| **`contents:`** | `read` | `write` — it can push fixes |

The modes are why they cannot be one job. Supplying a `prompt` puts the action
in agent mode for *every* event it sees, so a single job with both triggers
would answer `@claude` comments in agent mode: no PR context, no tracking
comment, and nothing posted back. They could share one file as two guarded jobs;
they are kept apart so each file's permissions and tools say what they mean.

The 👀 reaction on an `@claude` comment comes from the Claude GitHub App
acknowledging the mention. It is **not** evidence that anything ran — the work
happens in `claude-mention.yml`, and if that workflow is missing or not yet on
`main`, the eyes are all you ever get.

**Artifacts:** both upload `claude-<workflow>-logs-*`, containing
`execution-output.json` (the action's own transcript) and `sessions/` (the raw
Claude Code session JSONL). The action otherwise discards these with the runner,
and the job log alone shows only `init` and `result`. Reach for these first when
a run is green but posted nothing. Note this repo is public, so these artifacts
and the `show_full_output` job logs are world-readable — they carry full tool
output, so don't put anything into CI you wouldn't publish.

**Where the logic lives:** both workflows are thin callers of [jantman/github-
actions-workflows](https://github.com/jantman/github-actions-workflows),
pinned at `@v1`. This file keeps only what a composite action cannot reach,
because by the time one runs the runner is up and the token is minted: the
triggers, `concurrency`, `permissions`, the fork guard, the trigger guard, and
`actions/checkout`. Change the behaviour there, not here — and note that a
change *there* is testable on its own PR, whereas a change to these files is
not.

**What a run posts:** the review deliberately does *not* pass `--comment` to
the review plugin. In that mode the plugin posts each finding as a standalone
inline comment and gives the run no top-level body to hang a summary or a cost
figure off. Instead the agent writes its findings to a JSON file and a later
step turns them into exactly **one** GitHub review (`POST /pulls/N/reviews`):
the findings as batched inline comments, and the summary plus the run's cost
footer in the body. Every run posts one review, including a run that decided
to skip. The review is authored by `github-actions[bot]`, not `claude[bot]` —
the action revokes its own App token before that step runs — so the body opens
with an explicit attribution line and carries a hidden `<!-- claude-code-
review -->` marker that later runs use to find it.

**A denied tool call now fails the check.** Both workflows parse the run's
result block and put duration, turn count, cost and `permission_denials_count`
in the job summary; the review also puts them in its footer. A non-zero denial
count, or `is_error`, fails the job. A denied `Skill` or `Task` is exactly how
these runs used to finish green having done nothing. Relatedly, if the agent
ends its turn without writing the findings file, the run posts its raw final
message with a warning banner and fails — it does not pass quietly.

**Who can trigger the mention workflow:** only comment/issue/review authors
whose `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`. This
repository is public and that job has `contents: write` and blanket `Bash`, so
without the check any passer-by who types the mention would get an agent run
billed to the maintainer's account. The field has to be read per-event: on
`issue_comment`, `github.event.issue.author_association` is the issue's
*opener*, not the commenter.

**Re-review on new commits:** the upstream `/code-review` plugin stops without
posting if Claude has already commented on the PR, which would make every push
after the first review a silent no-op. `claude-pr-review.yml` overrides that in
its `prompt` and scopes re-reviews to the commits since Claude's last review.

### 🔒 `security.yml` - Security & Dependencies
**Triggers:** Weekly schedule, dependency file changes, manual dispatch
**Purpose:** Security scanning and dependency monitoring

**Jobs:**
- **Security Scan**: vulnerability scanning with pip-audit, safety, and bandit
- **Dependency Review**: License and security review for PRs

## Features

### PR Integration
- **Coverage Comments**: Automatic coverage percentage comments on PRs
- **Artifact Upload**: Debug information uploaded on test failures
- **Test Summary**: Consolidated pass/fail status across all test suites

### Caching
- **Pip Dependencies**: Cached based on requirements file hashes
- **Retention**: Artifacts retained for 7-30 days based on type

### Python Version
- **Target Version**: 3.13 (latest stable release)
- **Simplified Setup**: Single version testing for faster CI

## Usage

### Manual Workflow Dispatch
```bash
# Trigger security scan manually
gh workflow run security.yml
```

### Local Testing Before Push
```bash
# Run the same commands as CI
nox -s tests     # Unit tests
nox -s coverage  # Coverage report
nox -s e2e       # E2E tests
```

### Viewing Results
- **GitHub UI**: Check Actions tab for workflow results
- **PR Comments**: Coverage percentage automatically commented
- **Artifacts**: Download debug information from failed runs

## Troubleshooting

### E2E Test Failures
1. Check `test-debug-output/` artifact for screenshots and HTML dumps
2. Review console logs in captured debug information
3. Examine page state JSON for context

### Coverage Issues
1. HTML coverage report available in `coverage-reports` artifact
2. XML report uploaded to Codecov (if configured)
3. Minimum threshold: 80%

### Dependency Issues
1. Security reports available in `security-reports` artifact
2. Dependency review blocks PRs with security issues
3. Weekly automated scans detect new vulnerabilities