#!/bin/bash
# Reads hook JSON from stdin, checks if the bash command is dangerous.
# Exit 0 = allow, exit 2 = block (shows error to model).
INPUT=$(cat)
TOOL=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

DANGEROUS='rm -rf|git push.*--force|git reset --hard|DROP TABLE|DELETE FROM|chmod -R 777|mkfs|dd if=|> /dev/'
if echo "$TOOL" | grep -qiE "$DANGEROUS"; then
  echo "BLOCKED: dangerous command detected: $TOOL"
  exit 2
fi
exit 0
