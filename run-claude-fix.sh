#!/bin/bash
# Survivor correction-plan runner — interactive Claude Code, attachable via tmux
cd ~/Documents/GitHub/survivor-game
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
exec claude --dangerously-skip-permissions \
  "Read docs/TASK-correction-plan.md and execute it fully to completion without stopping to ask questions. ultrathink"
