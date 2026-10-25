#!/bin/sh
# Install Flapclock for the local machine. Ubuntu 22.04 and newer.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
if [ -z "${PREFIX:-}" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    PREFIX=/usr/local
  else
    PREFIX="${HOME}/.local"
  fi
fi
LIB="$PREFIX/lib"
BIN="$PREFIX/bin"
APP="$PREFIX/share/applications"

if ! python3 -c 'import gi,cairo; gi.require_version("Gtk","3.0"); from gi.repository import Gtk' 2>/dev/null; then
  echo "請先安裝：sudo apt install python3-gi python3-cairo gir1.2-gtk-3.0 gir1.2-pango-1.0" >&2
  exit 1
fi

install -d "$LIB/flapclock" "$BIN" "$APP"
install -m 0644 "$ROOT"/flapclock/*.py "$LIB/flapclock/"
cat > "$BIN/flapclock" << EOF
#!/bin/sh
export PYTHONPATH=$LIB\${PYTHONPATH:+:\$PYTHONPATH}
exec /usr/bin/python3 -m flapclock "\$@"
EOF
chmod 0755 "$BIN/flapclock"

sed "s|@BIN@|$BIN/flapclock|g" "$ROOT/data/flapclock.desktop" > "$APP/flapclock.desktop"
sed "s|@BIN@|$BIN/flapclock|g" "$ROOT/data/flapclock-screensaver.desktop" > "$APP/flapclock-screensaver.desktop"
chmod 0644 "$APP/flapclock.desktop" "$APP/flapclock-screensaver.desktop"

AUTO_HOME=$HOME
AUTO_OWNER=
if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
  AUTO_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
  AUTO_OWNER=$SUDO_USER
fi
AUTO="${XDG_CONFIG_HOME:-$AUTO_HOME/.config}/autostart"
if [ ! -d "$AUTO" ]; then
  if [ -n "$AUTO_OWNER" ]; then
    install -d -o "$AUTO_OWNER" -g "$AUTO_OWNER" "$AUTO"
  else
    install -d "$AUTO"
  fi
fi
sed "s|@BIN@|$BIN/flapclock|g" "$ROOT/data/flapclock-autostart.desktop" > "$AUTO/flapclock.desktop"
chmod 0644 "$AUTO/flapclock.desktop"
if [ -n "$AUTO_OWNER" ]; then
  chown "$AUTO_OWNER:" "$AUTO/flapclock.desktop"
fi

echo "已安裝 $BIN/flapclock"
echo "桌面小工具會在登入時啟動。立刻試跑：$BIN/flapclock"
