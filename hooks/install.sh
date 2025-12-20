#!/bin/bash
# Install git hooks for this repository

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_HOOKS_DIR="$(git rev-parse --git-dir)/hooks"

echo "Installing git hooks..."

# Install pre-commit hook
if [ -f "$GIT_HOOKS_DIR/pre-commit" ]; then
    echo "⚠️  pre-commit hook already exists. Backing up to pre-commit.backup"
    mv "$GIT_HOOKS_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit.backup"
fi

cp "$SCRIPT_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit"
chmod +x "$GIT_HOOKS_DIR/pre-commit"

echo "✅ Pre-commit hook installed successfully!"
echo ""
echo "The hook will:"
echo "  • Remind you to regenerate screenshots when UI files change"
echo "  • Prevent commits without screenshot updates (with option to skip)"
echo ""
echo "To uninstall: rm $GIT_HOOKS_DIR/pre-commit"
