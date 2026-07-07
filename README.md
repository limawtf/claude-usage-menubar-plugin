# Claude Usage in the macOS Menu Bar

**See your Claude Pro / Max subscription usage as a percentage right in the macOS menu bar** — a SwiftBar plugin that shows your Claude Code 5-hour session limit and weekly limit like a battery, color-coded, with reset times. The numbers are *exact*, pulled from the same official endpoint as Claude Code's `/usage` command.

If you've ever asked *"how do I see my Claude Code usage in the Mac menu bar?"* or *"how much of my Claude Max quota is left right now?"* — this is that. An always-on Claude usage indicator that lives in your menu bar.

---

## What it shows

**In the menu bar:** a colored dot + your 5-hour session usage percentage.

- 🟢 green `< 50%` · 🟡 yellow `< 80%` · 🟠 orange `< 95%` · 🔴 red `≥ 95%`

**In the dropdown:**

- **5h (session)** — battery-style bar with `%` of the rolling 5-hour session limit + reset time.
- **Weekly** — battery-style bar with `%` of the weekly limit + reset time.
- Optional **weekly Opus / Sonnet** breakdown when present.
- **API spend** (optional) — today / last 7 days / this month / lifetime dollar cost, via [`ccusage`](https://github.com/ryoppippi/ccusage).
- **Refresh** — forces an immediate live update.

Reset times are rounded to the hour and shown in your local time. The plugin self-heals when the 5-hour window rolls over.

---

## Requirements

- **macOS**
- **[SwiftBar](https://github.com/swiftbar/SwiftBar)** — `brew install --cask swiftbar`
- **Logged into Claude Code** — so the OAuth token exists in your macOS Keychain (this is what the plugin reads to query your usage).
- *Optional:* **[`ccusage`](https://github.com/ryoppippi/ccusage)** — `npm install -g ccusage` — for the dollar API spend section. If it's not installed, that section is simply hidden and the usage `%` still works.

The plugin itself is a single file using only the Python standard library, so the system `python3` that ships with macOS is enough. No virtualenv, no pip, no dependencies. Works on both Apple Silicon (`/opt/homebrew/bin`) and Intel (`/usr/local/bin`).

---

## Install

```bash
git clone https://github.com/limawtf/claude-usage-menubar-plugin
cd claude-usage-menubar
./install.sh
```

`install.sh` is idempotent and does the following:

1. Ensures **SwiftBar** is installed (`brew install --cask swiftbar`) and, if `npm` is available, installs **`ccusage`**.
2. **Picks the plugin directory** — if SwiftBar already has a `PluginDirectory` set (`defaults read com.ameba.SwiftBar PluginDirectory`) and it exists, it uses *that* (so an existing SwiftBar setup is never hijacked). Otherwise it uses `~/.config/swiftbar-plugins` and points SwiftBar's `PluginDirectory` there.
3. **Symlinks** `claude-usage.1m.py` from the cloned repo into the plugin directory (with an explicit destination filename).
4. Adds **SwiftBar as a macOS login item** (idempotent), launches it, and triggers a refresh via `open swiftbar://refreshallplugins`.
5. Prints clear next steps.

### Quick install with Claude Code

Prefer to let your AI coding agent do it? Paste this prompt into **Claude Code**:

```
Clone https://github.com/limawtf/claude-usage-menubar-plugin into a sensible local
directory and run ./install.sh from inside it. The script is idempotent: it
installs SwiftBar (brew cask) and, if npm is present, ccusage; picks the right
SwiftBar plugin directory; symlinks the plugin; adds SwiftBar as a login item;
launches it and triggers a refresh. After it finishes, tell me the next steps
it printed — especially the one-time Keychain "Always Allow" prompt I need to
approve on first run, and confirm I'm logged into Claude Code.
```

Any AI coding agent can run the installer for you, end to end.

### Fallback (fully manual)

If you'd rather wire it up by hand:

```bash
# 1. install SwiftBar
brew install --cask swiftbar

# 2. point SwiftBar at a plugin folder (skip if you already have one)
mkdir -p ~/.config/swiftbar-plugins
defaults write com.ameba.SwiftBar PluginDirectory "$HOME/.config/swiftbar-plugins"

# 3. symlink the plugin in (note the .1m = refresh every 1 minute)
ln -sf "$PWD/claude-usage.1m.py" "$HOME/.config/swiftbar-plugins/claude-usage.1m.py"

# 4. launch SwiftBar (and refresh)
open -a SwiftBar
open "swiftbar://refreshallplugins"
```

The `.1m` in `claude-usage.1m.py` tells SwiftBar to re-run the plugin every minute.

> **First run:** macOS shows a one-time Keychain prompt asking whether `python3` may read the Claude Code credentials. Click **Always Allow** so the plugin can keep reading your token silently. Make sure you're logged into Claude Code first, or there's no token to read.

---

## How it works

The plugin reads the OAuth token that **Claude Code** stores in the macOS Keychain (service `Claude Code-credentials`) and calls the exact endpoint that powers Claude Code's `/usage` command:

```
GET https://api.anthropic.com/api/oauth/usage
Header: anthropic-beta: oauth-2025-04-20
Authorization: Bearer <oauth token from Keychain>
```

This is a **metadata endpoint**. It reports how much of your 5-hour session limit and weekly limit you've consumed — it does **not** consume tokens and does **not** count against your plan limit. Because the data comes straight from Anthropic's own accounting, the percentages are **exact, not an estimate**.

The token never leaves your machine. It's read locally from the Keychain and sent only to `api.anthropic.com`.

**Caching & resilience:**

- Usage is cached for ~300s (the endpoint has its own rate limit). On HTTP `429`, the plugin falls back to the last good value instead of breaking.
- Cost (`ccusage`) is cached for ~180s.
- Caches live in `~/Library/Caches/claude-usage-menubar/` (per-user, `0700`); no token is ever written to disk.
- When the rolling 5-hour window rolls over, the plugin detects it and self-heals on the next refresh.

---

## Notes

- **One-time Keychain prompt:** on first run, approve with **Always Allow** (see above).
- **`ccusage` is optional:** without it, the "API spend" section is hidden; the usage `%` continues to work normally.

### Uninstall

```bash
# remove the plugin symlink (adjust path if you use a custom plugin dir)
rm -f "$HOME/.config/swiftbar-plugins/claude-usage.1m.py"

# remove caches
rm -rf "$HOME/Library/Caches/claude-usage-menubar"

# refresh or quit SwiftBar
osascript -e 'quit app "SwiftBar"'
```

If SwiftBar was added as a login item and you no longer want it: **System Settings → General → Login Items**, remove SwiftBar. To remove SwiftBar entirely: `brew uninstall --cask swiftbar`.

---

## FAQ / Troubleshooting

**The bar shows an error or no percentage.**
Most likely the token expired or is missing. Open **Claude Code** and make sure you're logged in — that refreshes the credentials in the Keychain. Then click **Refresh** in the dropdown (or `open swiftbar://refreshallplugins`).

**It keeps re-prompting for Keychain access.**
You clicked "Allow" instead of "Always Allow". Trigger a refresh and choose **Always Allow** on the next prompt.

**Am I being rate limited / will this burn my quota?**
No. The `oauth/usage` endpoint is metadata only — it does not consume tokens or your plan limit. If the endpoint itself returns `429`, the plugin keeps showing the last good value until it can fetch again.

**The reset time looks off by a few minutes.**
Reset times are intentionally rounded to the hour and shown in your local time zone, so a few minutes' difference is expected.

**I already use SwiftBar with other plugins.**
The installer detects your existing `PluginDirectory` and installs into it — it won't move or hijack your setup.

**The API spend section is missing.**
That section requires `ccusage` (`npm install -g ccusage`). Without it, only the usage percentages are shown.

---

## Why

Claude Code's `/usage` answers *"how much have I used?"* — but only when you stop and ask. This puts the answer where you can glance at it all day: your Claude Pro/Max usage, the 5-hour session and weekly limit, color-coded like a battery, always one look away.

## License

[MIT](LICENSE).
