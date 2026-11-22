#!/bin/bash
# 세월의 사연극장 — 맥북 원클릭 실행
# 더블클릭하면 필요한 것을 자동으로 설치하고 브라우저를 엽니다.
cd "$(dirname "$0")" || exit 1
set -u

BOLD="\033[1m"; GOLD="\033[33m"; RED="\033[31m"; GREEN="\033[32m"; NC="\033[0m"
say() { printf "%b\n" "$1"; }
pause_exit() { say "\n${BOLD}Enter 키를 누르면 창이 닫힙니다.${NC}"; read -r _; exit "${1:-1}"; }

say "${GOLD}${BOLD}"
say "  ┌──────────────────────────────────────────────┐"
say "  │        세월의 사연극장 · 자동화 스튜디오      │"
say "  │   대본 → 성우 → 이미지 → 영상 → 썸네일       │"
say "  └──────────────────────────────────────────────┘"
say "${NC}"

# 1) Python 3 확인
if ! command -v python3 >/dev/null 2>&1; then
  say "${RED}Python 3 가 없습니다.${NC}"
  say "https://www.python.org/downloads/macos/ 에서 Python 3.10 이상을 설치한 뒤 다시 실행해 주세요."
  say "(또는 터미널에서: brew install python)"
  pause_exit 1
fi
PYVER=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
say "· Python ${PYVER} 확인"

# 2) ffmpeg 확인
if ! command -v ffmpeg >/dev/null 2>&1; then
  say "${RED}ffmpeg 가 설치되어 있지 않습니다.${NC} 영상 조립에 꼭 필요합니다."
  if command -v brew >/dev/null 2>&1; then
    say "터미널에서  ${BOLD}brew install ffmpeg${NC}  를 실행하면 됩니다."
    printf "지금 자동으로 설치할까요? (y/N) "
    read -r ans
    if [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ]; then
      brew install ffmpeg || { say "${RED}설치에 실패했습니다.${NC}"; pause_exit 1; }
    else
      say "설치 후 이 파일을 다시 더블클릭해 주세요."
      pause_exit 1
    fi
  else
    say "먼저 Homebrew 를 설치해 주세요:  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    say "그다음  brew install ffmpeg  를 실행합니다."
    pause_exit 1
  fi
fi
say "· ffmpeg 확인: $(ffmpeg -version 2>/dev/null | head -1 | cut -c1-60)"

# 3) 가상환경
if [ ! -d ".venv" ]; then
  say "· 처음 실행이라 전용 환경을 만듭니다 (1~2분)…"
  python3 -m venv .venv || { say "${RED}가상환경 생성 실패${NC}"; pause_exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip -q >/dev/null 2>&1
say "· 필요한 프로그램 설치 확인 중 (처음엔 3~5분 걸립니다)…"
if ! python -m pip install -q -r requirements.txt; then
  say "${RED}설치에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행해 주세요.${NC}"
  pause_exit 1
fi
say "· 설치 완료"

# 4) 포트 찾기 (8765 부터)
PORT=8765
for p in 8765 8766 8767 8768 8769; do
  if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then PORT=$p; break; fi
done

mkdir -p logs
say ""
LANIP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
say "${GREEN}${BOLD}▶ http://localhost:${PORT} 에서 화면을 엽니다.${NC}"
say "   같은 와이파이의 폰에서는  http://${LANIP}:${PORT}  로 접속하세요."
say "   (브라우저가 자동으로 열리지 않으면 주소를 직접 입력하세요)"
say "   이 창을 닫으면 스튜디오가 종료됩니다."
say ""

# 자동 재시작([🔄 최신 버전 업데이트]) 때 같은 포트를 쓰도록 미리 알려 둔다
export SEWOL_PORT="$PORT"
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --log-level warning &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1
}
trap cleanup EXIT INT TERM

# 서버가 뜰 때까지 기다렸다가 브라우저 열기
for i in $(seq 1 40); do
  if curl -s "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
open "http://localhost:${PORT}" >/dev/null 2>&1 || true

wait "$SERVER_PID"
