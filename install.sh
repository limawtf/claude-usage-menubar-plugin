#!/usr/bin/env bash
set -euo pipefail

# install.sh — Claude usage menu bar indicator (SwiftBar plugin)
# Shows your Claude Pro/Max subscription usage like a battery: % of the rolling
# 5-hour session limit and the weekly limit, with reset times. Optional dollar
# cost section via the 'ccusage' CLI.

REPO_OWNER="limawtf"
REPO_NAME="claude-usage-menubar-plugin"
PLUGIN_FILE="claude-usage.1m.py"
SWIFTBAR_BUNDLE_ID="com.ameba.SwiftBar"
DEFAULT_PLUGIN_DIR="$HOME/.config/swiftbar-plugins"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m  ! \033[0m%s\n' "$*"; }
die()   { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# resolve this script's own directory (so we can find the plugin file)
# ---------------------------------------------------------------------------
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

PLUGIN_SRC="$SCRIPT_DIR/$PLUGIN_FILE"

# ---------------------------------------------------------------------------
# 1. sanity checks
# ---------------------------------------------------------------------------
info "Checking environment"

[[ "$(uname -s)" == "Darwin" ]] || die "This installer only runs on macOS."
ok "macOS detected"

# python3 must be a working interpreter (the plugin's shebang is /usr/bin/env python3)
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys' >/dev/null 2>&1; then
  die "A working python3 was not found. Install the Xcode Command Line Tools (run: xcode-select --install) and re-run ./install.sh"
fi
ok "python3 available: $(command -v python3)"

[[ -f "$PLUGIN_SRC" ]] || die "Could not find $PLUGIN_FILE next to install.sh (expected at: $PLUGIN_SRC). Run ./install.sh from the cloned $REPO_OWNER/$REPO_NAME repo."
ok "Found plugin: $PLUGIN_SRC"

# ---------------------------------------------------------------------------
# 2. locate Homebrew (Apple Silicon /opt/homebrew, Intel /usr/local)
# ---------------------------------------------------------------------------
info "Locating Homebrew"

BREW=""
if command -v brew >/dev/null 2>&1; then
  BREW="$(command -v brew)"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  BREW="/opt/homebrew/bin/brew"
elif [[ -x /usr/local/bin/brew ]]; then
  BREW="/usr/local/bin/brew"
fi

[[ -n "$BREW" ]] || die "Homebrew not found. Install it from https://brew.sh and re-run ./install.sh"
eval "$("$BREW" shellenv)"
ok "Homebrew: $BREW"

# ---------------------------------------------------------------------------
# 3. ensure SwiftBar
# ---------------------------------------------------------------------------
info "Ensuring SwiftBar is installed"

if [[ -d "/Applications/SwiftBar.app" ]] || "$BREW" list --cask swiftbar >/dev/null 2>&1; then
  ok "SwiftBar already installed"
else
  info "Installing SwiftBar (brew install --cask swiftbar)"
  "$BREW" install --cask swiftbar
  ok "SwiftBar installed"
fi

# ---------------------------------------------------------------------------
# 4. ensure ccusage (optional, non-fatal)
# ---------------------------------------------------------------------------
info "Checking optional dependency: ccusage (for the dollar cost section)"

if command -v ccusage >/dev/null 2>&1; then
  ok "ccusage already installed"
elif command -v npm >/dev/null 2>&1; then
  info "Installing ccusage (npm install -g ccusage)"
  if npm install -g ccusage; then
    ok "ccusage installed"
  else
    warn "ccusage install failed — the cost section will be hidden, but usage % still works."
  fi
else
  warn "npm not found — skipping ccusage. The cost section will be hidden; usage % still works."
fi

# ---------------------------------------------------------------------------
# 5. choose plugin directory
#    - respect an existing SwiftBar PluginDirectory (don't hijack a setup)
#    - else use ~/.config/swiftbar-plugins and set it via `defaults write`
# ---------------------------------------------------------------------------
info "Determining SwiftBar plugin directory"

EXISTING_DIR="$(defaults read "$SWIFTBAR_BUNDLE_ID" PluginDirectory 2>/dev/null || true)"
# expand a leading ~ if present
case "$EXISTING_DIR" in
  "~"|"~/"*) EXISTING_DIR="${HOME}/${EXISTING_DIR#\~/}";;
esac

if [[ -n "$EXISTING_DIR" && -d "$EXISTING_DIR" ]]; then
  PLUGIN_DIR="$EXISTING_DIR"
  ok "Using existing SwiftBar plugin directory: $PLUGIN_DIR"
else
  PLUGIN_DIR="$DEFAULT_PLUGIN_DIR"
  mkdir -p "$PLUGIN_DIR"
  defaults write "$SWIFTBAR_BUNDLE_ID" PluginDirectory "$PLUGIN_DIR"
  ok "Set SwiftBar plugin directory to: $PLUGIN_DIR"
fi

# ---------------------------------------------------------------------------
# 6. symlink the plugin (explicit destination filename, never into a dir)
# ---------------------------------------------------------------------------
info "Linking plugin into place"

PLUGIN_DEST="$PLUGIN_DIR/$PLUGIN_FILE"

# If a directory somehow exists at the destination path, refuse to clobber it.
if [[ -d "$PLUGIN_DEST" && ! -L "$PLUGIN_DEST" ]]; then
  die "Refusing to overwrite a directory at $PLUGIN_DEST — please remove it manually."
fi

# Remove any prior file/symlink at the exact destination, then link.
rm -f "$PLUGIN_DEST"
ln -s "$PLUGIN_SRC" "$PLUGIN_DEST"
chmod +x "$PLUGIN_SRC"
ok "Linked $PLUGIN_DEST -> $PLUGIN_SRC"

# ---------------------------------------------------------------------------
# 7. add SwiftBar as a login item (idempotent)
# ---------------------------------------------------------------------------
info "Registering SwiftBar as a login item"

LOGIN_PRESENT="$(osascript -e 'tell application "System Events" to get the name of every login item' 2>/dev/null | tr ',' '\n' | grep -i 'SwiftBar' || true)"
if [[ -n "$LOGIN_PRESENT" ]]; then
  ok "SwiftBar already a login item"
else
  if osascript -e 'tell application "System Events" to make login item at end with properties {path:"/Applications/SwiftBar.app", hidden:false}' >/dev/null 2>&1; then
    ok "Added SwiftBar to login items"
  else
    warn "Could not add SwiftBar to login items automatically (add it in System Settings > General > Login Items)."
  fi
fi

# ---------------------------------------------------------------------------
# 8. launch SwiftBar and trigger a refresh
# ---------------------------------------------------------------------------
info "Launching SwiftBar and refreshing plugins"

open -a SwiftBar || warn "Could not launch SwiftBar automatically — open it from /Applications."
# give SwiftBar a moment to come up before asking it to refresh
/bin/sleep 2
open "swiftbar://refreshallplugins" >/dev/null 2>&1 || true
ok "Refresh triggered"

# ---------------------------------------------------------------------------
# done — next steps
# ---------------------------------------------------------------------------
cat <<EOF

──────────────────────────────────────────────────────────────────────────
 Installed: Claude usage menu bar indicator
──────────────────────────────────────────────────────────────────────────

 What you'll see:
   A colored dot in the menu bar (green < 50%, yellow < 80%, orange < 95%,
   red >= 95%) followed by your 5-hour session usage %. The dropdown shows the
   5h (session) and weekly bars with reset times, optional weekly Opus/Sonnet,
   and an "API spend" cost section (today / 7 days / month / lifetime) when
   ccusage is available. Use "Refresh" to force a live update.

 Next steps:
   1. Make sure you are logged into Claude Code on this Mac. The indicator
      reads the OAuth token Claude Code stores in the macOS Keychain
      (service "Claude Code-credentials"). Without it, there is no data.

   2. On first run you'll get a one-time macOS Keychain prompt asking for
      permission to read that token. Click "Always Allow" so it stops asking.

   3. If you don't see the indicator yet, click the SwiftBar icon and pick
      Refresh, or run:  open "swiftbar://refreshallplugins"

 Notes:
   • Plugin linked at: $PLUGIN_DEST
   • The usage figure is EXACT (it reads the same subscription metadata
     endpoint Claude Code's /usage uses) and does NOT consume tokens.
   • The dollar cost section is optional; it only appears when 'ccusage' is
     installed (npm install -g ccusage).
──────────────────────────────────────────────────────────────────────────
EOF
