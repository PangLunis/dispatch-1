#!/bin/bash
# Nightly memory consolidation wrapper
# Runs memory consolidation, chat-context, and fact injection sequentially.
# Used by the ephemeral task system as a script-mode task.
#
# Pipeline:
#   1. consolidate_memory.py --all   → facts table (Haiku scan + Sonnet verify)
#   2. consolidate_chat.py --all     → CONTEXT.md per group chat (Sonnet)
#   3. fact inject --all             → facts table → CLAUDE.md ## Active Facts
#
# Exit codes (bitfield):
#   0 = all passed
#   1 = memory consolidation failed
#   2 = chat-context failed
#   4 = fact injection failed
#   Examples: 3 = memory+chat, 5 = memory+inject, 7 = all three

set -o pipefail
# Note: set -e is intentionally omitted. This script captures exit codes
# manually to report partial failures. set -e would conflict with the
# || exit_code=$? pattern inside command substitutions.

MEMORY_CONSOLIDATION="$HOME/dispatch/prototypes/memory-consolidation/consolidate_memory.py"
CHAT_CONTEXT="$HOME/dispatch/prototypes/memory-consolidation/consolidate_chat.py"
FACT_CLI="$HOME/dispatch/scripts/fact"

echo "=== Memory Consolidation (→ facts table, Haiku+Sonnet) ==="
mc_output=$(uv run "$MEMORY_CONSOLIDATION" --all 2>&1) && mc_exit=0 || mc_exit=$?
echo "$mc_output"

echo ""
echo "=== Chat Context Consolidation (→ CONTEXT.md per group chat) ==="
cc_output=$(uv run "$CHAT_CONTEXT" --all --groups-only 2>&1) && cc_exit=0 || cc_exit=$?
echo "$cc_output"

echo ""
echo "=== Fact Injection (→ CLAUDE.md ## Active Facts) ==="
fi_output=$(uv run "$FACT_CLI" inject --all 2>&1) && fi_exit=0 || fi_exit=$?
echo "$fi_output"

echo ""
echo "=== Summary ==="
failures=0
[ $mc_exit -ne 0 ] && failures=$((failures + 1)) && echo "❌ Memory consolidation failed (exit=$mc_exit)"
[ $cc_exit -ne 0 ] && failures=$((failures + 1)) && echo "❌ Chat-context failed (exit=$cc_exit)"
[ $fi_exit -ne 0 ] && failures=$((failures + 1)) && echo "❌ Fact injection failed (exit=$fi_exit)"

if [ $failures -eq 0 ]; then
    echo "✅ All consolidation passes completed successfully"
    exit 0
else
    echo "⚠️ $failures of 3 passes failed"
    exit_code=0
    [ $mc_exit -ne 0 ] && exit_code=$((exit_code | 1))
    [ $cc_exit -ne 0 ] && exit_code=$((exit_code | 2))
    [ $fi_exit -ne 0 ] && exit_code=$((exit_code | 4))
    exit $exit_code
fi
