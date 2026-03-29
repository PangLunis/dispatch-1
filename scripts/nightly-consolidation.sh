#!/bin/bash
# Nightly memory consolidation wrapper
# Runs person-facts, chat-context, and fact-extraction scripts sequentially.
# Used by the ephemeral task system as a script-mode task.
#
# Exit codes (bitfield):
#   0 = all passed
#   1 = person-facts failed
#   2 = chat-context failed
#   3 = person-facts + chat-context failed
#   4 = fact-extraction failed
#   5 = person-facts + fact-extraction failed
#   6 = chat-context + fact-extraction failed
#   7 = all three failed

set -o pipefail
# Note: set -e is intentionally omitted. This script captures exit codes
# manually to report partial failures. set -e would conflict with the
# || exit_code=$? pattern inside command substitutions.

PERSON_FACTS="$HOME/dispatch/prototypes/memory-consolidation/consolidate_3pass.py"
CHAT_CONTEXT="$HOME/dispatch/prototypes/memory-consolidation/consolidate_chat.py"
FACT_EXTRACTION="$HOME/dispatch/prototypes/memory-consolidation/consolidate_facts.py"

echo "=== Person-Facts Consolidation (→ Contacts.app notes) ==="
pf_output=$(uv run "$PERSON_FACTS" --all 2>&1) && pf_exit=0 || pf_exit=$?
echo "$pf_output"

echo ""
echo "=== Chat Context Consolidation (→ CONTEXT.md per group chat) ==="
cc_output=$(uv run "$CHAT_CONTEXT" --all --groups-only 2>&1) && cc_exit=0 || cc_exit=$?
echo "$cc_output"

echo ""
echo "=== Fact Extraction (→ facts table + CLAUDE.md injection) ==="
fe_output=$(uv run "$FACT_EXTRACTION" --all 2>&1) && fe_exit=0 || fe_exit=$?
echo "$fe_output"

echo ""
echo "=== Summary ==="
failures=0
[ $pf_exit -ne 0 ] && failures=$((failures + 1)) && echo "❌ Person-facts failed (exit=$pf_exit)"
[ $cc_exit -ne 0 ] && failures=$((failures + 1)) && echo "❌ Chat-context failed (exit=$cc_exit)"
[ $fe_exit -ne 0 ] && failures=$((failures + 1)) && echo "❌ Fact-extraction failed (exit=$fe_exit)"

if [ $failures -eq 0 ]; then
    echo "✅ All consolidation passes completed successfully"
    exit 0
else
    echo "⚠️ $failures of 3 passes failed"
    # Exit code encodes which passes failed (bitfield):
    #   bit 0 (1) = person-facts failed
    #   bit 1 (2) = chat-context failed
    #   bit 2 (4) = fact-extraction failed
    # Examples: 3 = pf+cc, 5 = pf+fe, 7 = all three
    exit_code=0
    [ $pf_exit -ne 0 ] && exit_code=$((exit_code | 1))
    [ $cc_exit -ne 0 ] && exit_code=$((exit_code | 2))
    [ $fe_exit -ne 0 ] && exit_code=$((exit_code | 4))
    exit $exit_code
fi
