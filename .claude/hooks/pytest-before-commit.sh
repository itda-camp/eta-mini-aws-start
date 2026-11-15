#!/bin/sh
# 에이전트가 `git commit` 을 치려 할 때 먼저 테스트를 돈다. 실패하면 커밋을 막는다(exit 2).
# 「다음부터 커밋 전에 꼭 테스트해 줘」는 기억(CLAUDE.md)이 아니라 훅으로 보장한다.
set -u
input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)
case "$cmd" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac
cd "$CLAUDE_PROJECT_DIR" || exit 0
if ! out=$(uv run pytest -q 2>&1); then
  printf '커밋 차단 : 테스트 실패. 먼저 고치거나 원인을 보고하라.\n%s\n' "$(printf '%s' "$out" | tail -15)" >&2
  exit 2
fi
exit 0
