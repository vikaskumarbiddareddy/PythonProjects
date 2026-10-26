#!/data/data/com.termux/files/usr/bin/bash
# One-time setup of Marathon Trainer on an Android phone with Termux.
#
#   curl -fsSLo setup.sh https://raw.githubusercontent.com/vikaskumarbiddareddy/PythonProjects/main/marathon_app/termux/setup.sh
#   bash setup.sh
#
# Safe to run again: it updates the code and keeps your data and settings.
set -euo pipefail

CONF="$HOME/.marathon"
# Branch to install: BRANCH from the caller, else the one saved by a previous run.
SAVED_BRANCH="$(grep -s '^BRANCH=' "$CONF/env" | cut -d= -f2 || true)"
BRANCH="${BRANCH:-${SAVED_BRANCH:-main}}"
REPO="https://github.com/vikaskumarbiddareddy/PythonProjects.git"
SRC="$HOME/marathon-src"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

say "Updating Termux packages"
pkg update -y
pkg upgrade -y
pkg install -y python git curl termux-tools

say "Downloading Marathon Trainer ($BRANCH)"
if [ -d "$SRC/.git" ]; then
  git -C "$SRC" fetch --depth 1 origin "$BRANCH"
  git -C "$SRC" checkout -q -B "$BRANCH" FETCH_HEAD
else
  git clone -q --depth 1 -b "$BRANCH" "$REPO" "$SRC"
fi
APP="$SRC/marathon_app"

say "Installing Python packages (first time can take a while)"
if ! python -m pip install -r "$APP/requirements-termux.txt"; then
  say "Building pydantic-core from source; this needs Rust and can take 10-20 minutes"
  pkg install -y rust binutils
  python -m pip install -r "$APP/requirements-termux.txt"
fi
python -m pip install --no-deps garminconnect
# Optional: browser-like TLS for Garmin login. Only a prebuilt wheel, never a long compile.
python -m pip install --only-binary=:all: curl_cffi >/dev/null 2>&1 \
  || echo "(curl_cffi not available on Android; Garmin login will use plain requests)"

say "Writing private settings to $CONF"
mkdir -p "$CONF/data"
chmod 700 "$CONF"
if [ ! -f "$CONF/env" ]; then
  KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > "$CONF/env" <<EOF
APP_KEY=$KEY
ALLOWED_HOSTS=127.0.0.1,localhost
MARATHON_DB=$CONF/data/marathon.db
GARMIN_TOKENS=$CONF/garmin_tokens
PORT=8765
EOF
fi
if grep -q '^BRANCH=' "$CONF/env"; then
  sed -i "s|^BRANCH=.*|BRANCH=$BRANCH|" "$CONF/env"
else
  echo "BRANCH=$BRANCH" >> "$CONF/env"
fi
chmod 600 "$CONF/env"

say "Installing the 'marathon' command and shortcuts"
install -m 755 "$APP/termux/marathon" "$PREFIX/bin/marathon"
mkdir -p "$HOME/.shortcuts" "$HOME/.termux/boot"
printf '#!/data/data/com.termux/files/usr/bin/bash\nmarathon\n' > "$HOME/.shortcuts/Marathon"
printf '#!/data/data/com.termux/files/usr/bin/bash\nmarathon start\n' > "$HOME/.termux/boot/marathon"
chmod 700 "$HOME/.shortcuts/Marathon" "$HOME/.termux/boot/marathon"

marathon restart >/dev/null

cat <<'EOF'

All set!

  marathon          start the app and open it in Chrome
  marathon garmin   connect your Garmin account (password is not saved)
  marathon stop     stop the app
  marathon update   get the latest version (keeps your data)
  marathon status   is it running?

Next steps:
  1. Run:  marathon garmin
  2. Run:  marathon        -> in Chrome tap  ⋮ -> Install app  (or Add to Home screen)
  3. Optional: install "Termux:Widget" (home-screen button) and "Termux:Boot"
     (start on phone boot) from F-Droid, and open each once.
EOF
