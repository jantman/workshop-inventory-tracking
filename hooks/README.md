# Git Hooks

This directory contains git hooks to help maintain code quality and documentation.

## Available Hooks

### pre-commit

Reminds developers to regenerate screenshots when UI files are modified.

**Triggers when:**
- Templates are modified (`app/templates/**`)
- CSS files are modified (`app/static/css/**`)
- JavaScript files are modified (`app/static/js/**`)
- Screenshot test files are modified

**Actions:**
- Prompts user to confirm screenshots were regenerated
- Provides commands to regenerate if needed
- Allows skipping for non-visual changes

## Installation

### Quick Install

```bash
./hooks/install.sh
```

### Manual Install

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Usage

Once installed, the hooks run automatically before commits.

### Pre-commit Hook Workflow

When you commit UI changes:

1. Hook detects modified UI files
2. Prompts: "Did you update screenshots? (y/n/skip)"
3. Options:
   - **y** - Continue with commit
   - **n** - Abort commit, regenerate screenshots
   - **skip** - Bypass check (use sparingly)

### Regenerating Screenshots

```bash
# Generate all screenshots
nox -s screenshots

# Stage the updated screenshots
git add docs/images/screenshots/

# Commit everything together
git commit -m "Update UI and regenerate screenshots"
```

## Bypassing Hooks

If you need to bypass hooks (emergency fixes, non-visual changes):

```bash
# Skip all hooks for one commit
git commit --no-verify

# Or respond "skip" when prompted by the hook
```

**Note:** Use bypass sparingly. CI/CD will still check screenshots on PRs.

## Uninstalling

```bash
rm .git/hooks/pre-commit
```

## Hook Development

To modify hooks:

1. Edit files in `hooks/` directory
2. Test the hook manually: `.git/hooks/pre-commit`
3. Run install script to update: `./hooks/install.sh`

## CI/CD Integration

The pre-commit hook is complemented by CI/CD checks:

- **GitHub Actions** (`.github/workflows/screenshots.yml`)
  - Runs on PRs that modify UI files
  - Regenerates screenshots
  - Fails if screenshots are outdated
  - Provides download of regenerated screenshots

This ensures screenshots stay synchronized even if developers skip local hooks.
