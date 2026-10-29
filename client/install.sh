#!/usr/bin/env bash
# 빌더로그 설치 한 줄(macOS·WSL·리눅스):  curl -fsSL {{ORIGIN}}/install.sh | bash
# English:  curl -fsSL {{ORIGIN}}/en/install.sh | bash
# Windows 는 PowerShell 에서:  irm {{ORIGIN}}/install.ps1 | iex  (WSL 우분투 안에서 이 스크립트를 실행해 줘요)
# 하는 일: 도우미(~/builderlog/get.py) 받기 → AI 도구 연결(Claude Code·Codex MCP 한 줄) → 로그인(브라우저 이메일 6자리) → 기능 고르기·설치 → 하루 1번 업데이트(물어봄)
# 시작 전에 할 일을 보여 주고 확인받아요. 비밀값은 화면에 안 나오고, 다시 실행해도 안전해요.
set -eu
BASE="${BUILDERLOG_SERVER:-{{ORIGIN}}}"
ROOT="${BUILDERLOG_HOME:-$HOME/builderlog}"
# 안내 언어: 영어 주소(/en/install.sh)면 서버가 {{LANG}} 을 en 으로 채운다(아니면 빈 값). 없으면 지난번 고른 언어(~/builderlog/lang), 그것도 없으면 한국어.
BUILDERLOG_LANG="${BUILDERLOG_LANG:-{{LANG}}}"
if [ -z "$BUILDERLOG_LANG" ] && [ -f "$ROOT/lang" ]; then
  BUILDERLOG_LANG="$(head -n 1 "$ROOT/lang" | tr -d '[:space:]')"
fi
case "$BUILDERLOG_LANG" in en|ko) ;; *) BUILDERLOG_LANG="" ;; esac
export BUILDERLOG_LANG
say() { if [ "$BUILDERLOG_LANG" = en ]; then echo "$2"; else echo "$1"; fi; }
case "$(uname -s)" in
  Darwin|Linux) ;;
  *) say "Windows 는 PowerShell 에 이 한 줄을 붙여 넣어 주세요:  irm $BASE/install.ps1 | iex" "On Windows, paste this line into PowerShell:  irm $BASE/en/install.ps1 | iex"; exit 1 ;;
esac
if ! command -v python3 >/dev/null 2>&1; then
  say "python3 가 필요해요. macOS: xcode-select --install (또는 brew install python@3.12) · 우분투: sudo apt install -y python3 python3-venv" \
    "python3 is needed. macOS: xcode-select --install (or brew install python@3.12) · Ubuntu: sudo apt install -y python3 python3-venv"
  exit 1
fi
mkdir -p "$ROOT"
if [ -n "$BUILDERLOG_LANG" ]; then printf '%s\n' "$BUILDERLOG_LANG" > "$ROOT/lang"; fi
curl -fsSL "$BASE/get.py" -o "$ROOT/get.py.new"
mv "$ROOT/get.py.new" "$ROOT/get.py"
# 어디서 실행돼도 같은 한 줄: 사람이 터미널에 붙이면 대화형 마법사, AI 도구(Claude Code·Codex)가 대신 실행하면(화면이 터미널 아님)
# 질문 없이 도우미 받기 + AI 도구 연결까지만 → "이제 AI 에게 '빌더로그 시작해 줘'" → 그다음은 MCP setup 도구가 로그인·선택·설치를 이끈다.
if [ -n "${BUILDERLOG_YES:-}" ]; then
  exec python3 "$ROOT/get.py" wizard --yes
elif [ -z "${CLAUDECODE:-}${CLAUDE_CODE_ENTRYPOINT:-}${CODEX_SANDBOX:-}${CODEX_MANAGED_BY_NPM:-}" ] && [ -t 1 ] && (exec </dev/tty) 2>/dev/null; then
  exec python3 "$ROOT/get.py" wizard </dev/tty
else
  exec python3 "$ROOT/get.py" wizard --connect-only
fi
