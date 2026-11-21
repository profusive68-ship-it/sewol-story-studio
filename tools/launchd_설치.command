#!/bin/bash
# 맥이 켜지면 대시보드를 자동으로 켜 두는 설정(launchd)
cd "$(dirname "$0")/.." || exit 1
BASE="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.sewol.studio.plist"
if [ ! -x ".venv/bin/python" ]; then
  echo "먼저 start.command 를 한 번 실행해 주세요."
  read -r _; exit 1
fi
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sewol.studio</string>
  <key>ProgramArguments</key>
  <array><string>$BASE/.venv/bin/python</string><string>-m</string><string>uvicorn</string>
    <string>app.main:app</string><string>--host</string><string>0.0.0.0</string>
    <string>--port</string><string>8765</string></array>
  <key>WorkingDirectory</key><string>$BASE</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$BASE/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$BASE/logs/launchd.err.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" >/dev/null 2>&1
launchctl load "$PLIST" && echo "설정 완료. 맥이 켜지면 http://localhost:8765 가 자동으로 열립니다."
echo "해제하려면:  launchctl unload $PLIST"
read -r _ 2>/dev/null || true
