#!/bin/sh
# Install (or reinstall) the conversation-log watcher as a macOS LaunchAgent.
# Starts immediately and on every login. Idempotent: safe to re-run.
set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.thoughtbridge.conversation-log"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$(command -v python3)"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/conversation-log"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$PROJECT_DIR/tools/conversation-log.py</string>
    <string>watch</string>
    <string>--interval</string>
    <string>15</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>StandardOutPath</key>
  <string>$PROJECT_DIR/conversation-log/watcher.log</string>
  <key>StandardErrorPath</key>
  <string>$PROJECT_DIR/conversation-log/watcher.log</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>15</integer>
</dict>
</plist>
EOF

# Replace any existing instance, then start.
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"

echo "Installed and started: $LABEL"
echo "  plist:  $PLIST"
echo "  logs:   $PROJECT_DIR/conversation-log/"
echo "  status: launchctl print gui/\$UID/$LABEL"
