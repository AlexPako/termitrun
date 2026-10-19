#!/bin/sh
# Профиль iTerm2 «TermitRun» (неон-нуар): копирует Dynamic Profile в папку iTerm2.
# Запускается ТОЛЬКО вручную. Сам тренажёр этот скрипт не вызывает, ~/.zshrc не трогается.
#   sh tools/iterm/install.sh            — поставить (или обновить) профиль
#   sh tools/iterm/install.sh --remove   — удалить профиль
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
PROJECT=$(cd "$HERE/../.." && pwd)
DEST="$HOME/Library/Application Support/iTerm2/DynamicProfiles"
TARGET="$DEST/TermitRun.json"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$TARGET"
    echo "Профиль TermitRun удалён. iTerm2 уберёт его из списка сам."
    exit 0
fi

case "$PROJECT" in
    *"|"*|*"'"*|*"&"*|*'\'*|*'"'*)
        echo "В пути проекта есть | ' & \\ или \" — поставь профиль вручную." >&2; exit 1 ;;
esac
mkdir -p "$DEST"
sed "s|__TERMIT_DIR__|$PROJECT|g" "$HERE/TermitRun.json" > "$TARGET"
echo "Готово: $TARGET"
echo "iTerm2 → Profiles → TermitRun (или Cmd+O). Удалить: sh tools/iterm/install.sh --remove"
