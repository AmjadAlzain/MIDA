#!/bin/bash
#
# git_commit_push.sh - Commit and push current work to origin/OCR_Engine
#
# Usage: ./scripts/git_commit_push.sh [-m "commit message"]
#
# Must be run from the repository root directory.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BRANCH="OCR_Engine"
DEFAULT_MESSAGE="Add MIDA certificate draft/confirm CRUD with migrations, API, and tests"

# Parse arguments
COMMIT_MESSAGE="$DEFAULT_MESSAGE"
while getopts "m:" opt; do
    case $opt in
        m)
            COMMIT_MESSAGE="$OPTARG"
            ;;
        \?)
            echo -e "${RED}Invalid option: -$OPTARG${NC}" >&2
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Git Commit & Push Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check we're in repo root (look for .git directory)
if [ ! -d ".git" ]; then
    echo -e "${RED}Error: Must run from repository root (no .git directory found)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Running from repository root${NC}"

# Ensure we're on the correct branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo -e "${YELLOW}Current branch is '$CURRENT_BRANCH', switching to '$BRANCH'...${NC}"
    git checkout "$BRANCH"
else
    echo -e "${GREEN}✓ Already on branch '$BRANCH'${NC}"
fi

# Pull latest with rebase
echo ""
echo -e "${BLUE}Pulling latest changes with rebase...${NC}"
git pull --rebase origin "$BRANCH" || {
    echo -e "${RED}Error: Failed to pull/rebase. Please resolve conflicts manually.${NC}"
    exit 1
}
echo -e "${GREEN}✓ Pulled latest from origin/$BRANCH${NC}"

# Run make test (don't fail script if tests fail)
echo ""
echo -e "${BLUE}Running tests...${NC}"
if make test 2>/dev/null; then
    echo -e "${GREEN}✓ Tests passed${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Tests failed or 'make test' not available. Continuing anyway.${NC}"
fi

# Run make lint (don't fail script if lint fails)
echo ""
echo -e "${BLUE}Running linter...${NC}"
if make lint 2>/dev/null; then
    echo -e "${GREEN}✓ Linting passed${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Linting failed or 'make lint' not available. Continuing anyway.${NC}"
fi

# Stage all changes
echo ""
echo -e "${BLUE}Staging all changes...${NC}"
git add -A

# Check if there are staged changes
if git diff --cached --quiet; then
    echo ""
    echo -e "${YELLOW}No changes to commit. Working tree is clean.${NC}"
    exit 0
fi

# Show staged summary
echo ""
echo -e "${BLUE}Staged changes summary:${NC}"
echo -e "${BLUE}----------------------------------------${NC}"
git diff --cached --stat
echo -e "${BLUE}----------------------------------------${NC}"

# Commit
echo ""
echo -e "${BLUE}Committing with message:${NC}"
echo -e "  \"$COMMIT_MESSAGE\""
git commit -m "$COMMIT_MESSAGE"
echo -e "${GREEN}✓ Changes committed${NC}"

# Push
echo ""
echo -e "${BLUE}Pushing to origin/$BRANCH...${NC}"
git push origin "$BRANCH"
echo -e "${GREEN}✓ Pushed to origin/$BRANCH${NC}"

# Final success message
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ SUCCESS: All changes pushed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Branch: ${BLUE}$BRANCH${NC}"
echo -e "Remote: ${BLUE}origin/$BRANCH${NC}"
echo -e "Commit: ${BLUE}$(git rev-parse --short HEAD)${NC}"
echo ""
