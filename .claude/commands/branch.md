# Branch - Save and Resume Conversation Branches

Save the current conversation state before `/rewind`, allowing you to resume it later.

## Usage

The user will provide one of these commands:
- `save <name>` - Save current session as a named branch
- `list` - List all saved branches
- `resume <name>` - Show command to resume a branch
- `delete <name>` - Delete a saved branch

## Implementation

Execute the appropriate bash script based on the subcommand.

### For `save <name>`:

```bash
#!/bin/bash
set -e

BRANCH_NAME="$1"
if [ -z "$BRANCH_NAME" ]; then
    echo "Error: Branch name required. Usage: /branch save <name>"
    exit 1
fi

# Find project directory (path encoded with dashes)
PROJECT_PATH=$(pwd | sed 's|/|-|g')
PROJECT_DIR="$HOME/.claude/projects/$PROJECT_PATH"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: No Claude session directory found for this project"
    exit 1
fi

# Find most recently modified session file (current session)
CURRENT_SESSION=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)

if [ -z "$CURRENT_SESSION" ]; then
    echo "Error: No session file found"
    exit 1
fi

SESSION_ID=$(basename "$CURRENT_SESSION" .jsonl)

# Create branches directory
BRANCHES_DIR="$HOME/.claude/branches/$PROJECT_PATH"
mkdir -p "$BRANCHES_DIR"

# Copy session file
cp "$CURRENT_SESSION" "$BRANCHES_DIR/${BRANCH_NAME}.jsonl"

# Also copy file-history if it exists
if [ -d "$HOME/.claude/file-history/$SESSION_ID" ]; then
    cp -r "$HOME/.claude/file-history/$SESSION_ID" "$BRANCHES_DIR/${BRANCH_NAME}-file-history"
fi

echo "✓ Saved branch '$BRANCH_NAME'"
echo "  Session: $SESSION_ID"
echo "  You can now use /rewind and continue with a different approach."
echo "  To resume this branch later: /branch resume $BRANCH_NAME"
```

### For `list`:

```bash
#!/bin/bash

PROJECT_PATH=$(pwd | sed 's|/|-|g')
BRANCHES_DIR="$HOME/.claude/branches/$PROJECT_PATH"

if [ ! -d "$BRANCHES_DIR" ] || [ -z "$(ls -A "$BRANCHES_DIR"/*.jsonl 2>/dev/null)" ]; then
    echo "No saved branches for this project."
    exit 0
fi

echo "Saved branches:"
echo ""
for f in "$BRANCHES_DIR"/*.jsonl; do
    name=$(basename "$f" .jsonl)
    date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$f")
    size=$(du -h "$f" | cut -f1)
    echo "  $name  ($date, $size)"
done
```

### For `resume <name>`:

```bash
#!/bin/bash

BRANCH_NAME="$1"
if [ -z "$BRANCH_NAME" ]; then
    echo "Error: Branch name required. Usage: /branch resume <name>"
    exit 1
fi

PROJECT_PATH=$(pwd | sed 's|/|-|g')
BRANCHES_DIR="$HOME/.claude/branches/$PROJECT_PATH"
BRANCH_FILE="$BRANCHES_DIR/${BRANCH_NAME}.jsonl"

if [ ! -f "$BRANCH_FILE" ]; then
    echo "Error: Branch '$BRANCH_NAME' not found"
    echo "Available branches:"
    ls "$BRANCHES_DIR"/*.jsonl 2>/dev/null | xargs -I{} basename {} .jsonl | sed 's/^/  /'
    exit 1
fi

# Extract session ID from the file (it's in the user messages)
SESSION_ID=$(grep -o '"sessionId":"[^"]*"' "$BRANCH_FILE" | head -1 | cut -d'"' -f4)

# Copy branch back to sessions directory
PROJECT_DIR="$HOME/.claude/projects/$PROJECT_PATH"
cp "$BRANCH_FILE" "$PROJECT_DIR/${SESSION_ID}.jsonl"

# Copy file-history back if it exists
if [ -d "$BRANCHES_DIR/${BRANCH_NAME}-file-history" ]; then
    cp -r "$BRANCHES_DIR/${BRANCH_NAME}-file-history" "$HOME/.claude/file-history/$SESSION_ID"
fi

echo "Branch '$BRANCH_NAME' restored."
echo ""
echo "To resume in a new terminal, run:"
echo "  claude --resume $SESSION_ID"
```

### For `delete <name>`:

```bash
#!/bin/bash

BRANCH_NAME="$1"
if [ -z "$BRANCH_NAME" ]; then
    echo "Error: Branch name required. Usage: /branch delete <name>"
    exit 1
fi

PROJECT_PATH=$(pwd | sed 's|/|-|g')
BRANCHES_DIR="$HOME/.claude/branches/$PROJECT_PATH"

rm -f "$BRANCHES_DIR/${BRANCH_NAME}.jsonl"
rm -rf "$BRANCHES_DIR/${BRANCH_NAME}-file-history"

echo "✓ Deleted branch '$BRANCH_NAME'"
```

## Workflow Example

```
# You're exploring approach A
/branch save approach-a

# Rewind to try a different approach
/rewind

# Continue with approach B...

# Later, to get back to approach A:
/branch resume approach-a
# Then in a new terminal: claude --resume <session-id>
```
