#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# <xbar.title>Claude Usage</xbar.title>
# <xbar.version>1.2</xbar.version>
# <xbar.author>limawtf</xbar.author>
# <xbar.desc>macOS menu bar indicator for Claude Pro/Max usage (5h + weekly %), exact data from the official usage endpoint. Optional API cost via ccusage.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
"""
Claude usage indicator for the macOS menu bar (SwiftBar plugin).

LIMITS (exact %, same as Claude Code's /usage command):
  GET https://api.anthropic.com/api/oauth/usage  (header anthropic-beta: oauth-2025-04-20)
  authenticated with the OAuth token Claude Code stores in the macOS Keychain
  (service "Claude Code-credentials"). This is a metadata endpoint -> it does NOT
  consume tokens or your plan limit. The percentages are exact, not estimates.

API SPEND (optional, via the `ccusage` CLI): today / last 7 days / this month / lifetime.
  ccusage reads local transcripts (~5s) -> result is cached for COST_TTL seconds.

Pure Python standard library: the system python3 that ships with macOS is enough.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta, date

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"

CACHE_DIR = os.path.expanduser("~/Library/Caches/claude-usage-menubar")
USAGE_CACHE = os.path.join(CACHE_DIR, "usage.json")
COST_CACHE = os.path.join(CACHE_DIR, "cost.json")
USAGE_TTL = 300  # s; the usage endpoint has its own rate limit -> call at most every 5 min (avoids 429)
COST_TTL = 180   # s; ccusage is slowish -> recompute at most every 3 min

# Homebrew Apple Silicon (/opt/homebrew/bin) + Intel (/usr/local/bin); where node/ccusage live
BIN_PATHS = ["/opt/homebrew/bin", "/usr/local/bin"]

EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def out(line=""):
    print(line)


def _cache_write(path, obj):
    """Atomic write into a private (0700) per-user cache dir."""
    try:
        os.makedirs(CACHE_DIR, mode=0o700, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Limits (oauth/usage)
# --------------------------------------------------------------------------- #
def get_creds():
    """Read the OAuth token from the Keychain. Returns (access_token, subscription_type)."""
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        o = json.loads(raw)["claudeAiOauth"]
        return o["accessToken"], o.get("subscriptionType", "")
    except Exception:
        return None, None


def fetch_usage(token):
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _reset_passed(d):
    """True if the 5h window reset time has already passed (cache is stale: window rolled over)."""
    try:
        iso = (d.get("five_hour") or {}).get("resets_at")
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt <= datetime.now(timezone.utc)
    except Exception:
        return False


def get_usage(token):
    """Usage with cache (USAGE_TTL s) so we don't trip the endpoint's rate limit.
    Returns (data, stale): stale=None if fresh, else a reason (e.g. '429') served from old cache.
    Cache is invalidated immediately if the 5h reset has already passed (forces a refetch).
    """
    # fresh cache AND window not rolled over -> don't hit the API
    try:
        if time.time() - os.stat(USAGE_CACHE).st_mtime < USAGE_TTL:
            with open(USAGE_CACHE) as f:
                cached = json.load(f)
            if not _reset_passed(cached):
                return cached, None
    except Exception:
        pass
    # live fetch
    try:
        d = fetch_usage(token)
        _cache_write(USAGE_CACHE, d)
        return d, None
    except urllib.error.HTTPError as e:
        reason = "429 (busy)" if e.code == 429 else f"HTTP {e.code}"
    except Exception:
        reason = "offline"
    # fetch failed -> fall back to last good value if any
    try:
        with open(USAGE_CACHE) as f:
            return json.load(f), reason
    except Exception:
        return None, reason


# --------------------------------------------------------------------------- #
# API spend (ccusage) with cache
# --------------------------------------------------------------------------- #
def _augmented_path():
    # SwiftBar runs with a minimal PATH -> make sure homebrew (node/ccusage) is reachable
    return ":".join(BIN_PATHS) + ":/usr/bin:/bin:" + os.environ.get("PATH", "")


def _ccusage_bin():
    for p in BIN_PATHS:
        cand = os.path.join(p, "ccusage")
        if os.path.exists(cand):
            return cand
    return shutil.which("ccusage")


def _run_cc(binp, args):
    env = dict(os.environ)
    env["PATH"] = _augmented_path()
    r = subprocess.run([binp] + args, capture_output=True, text=True, timeout=40, env=env)
    return json.loads(r.stdout)


def compute_costs():
    # Calendar buckets (today / 7d / month / lifetime). We deliberately do NOT use ccusage's
    # "5h block" here: it anchors to round hours and does NOT line up with Anthropic's rolling
    # 5h window (the one behind the %), which was confusing. Also $ != % (the limit is weighted
    # by model, not dollars). So spend is reported over calendar buckets, never tied to the %.
    binp = _ccusage_bin()
    if not binp:
        return None
    try:
        dly = _run_cc(binp, ["daily", "--json"])
    except Exception:
        return None

    rows = dly.get("daily") or []
    totals = dly.get("totals") or {}
    today = date.today()
    tods = today.isoformat()
    ym = today.strftime("%Y-%m")
    since7 = (today - timedelta(days=6)).isoformat()  # includes today = 7 days

    def dk(r):
        return r.get("date") or r.get("period") or ""

    def cost(r):
        return r.get("totalCost") or r.get("costUSD") or 0

    today_c = sum(cost(r) for r in rows if dk(r) == tods)
    last7 = sum(cost(r) for r in rows if dk(r) >= since7)
    month = sum(cost(r) for r in rows if dk(r)[:7] == ym)
    lifetime = totals.get("totalCost", sum(cost(r) for r in rows))

    return {"today": today_c, "last7": last7, "month": month, "lifetime": lifetime}


def get_costs():
    """Costs cached for COST_TTL s. On error, fall back to old cache; else None."""
    try:
        if time.time() - os.stat(COST_CACHE).st_mtime < COST_TTL:
            with open(COST_CACHE) as f:
                return json.load(f)
    except Exception:
        pass
    data = compute_costs()
    if data is not None:
        _cache_write(COST_CACHE, data)
        return data
    try:
        with open(COST_CACHE) as f:
            return json.load(f)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def color(pct):
    if pct >= 95:
        return "#ff3b30"   # red
    if pct >= 80:
        return "#ff9500"   # orange
    if pct >= 50:
        return "#ffcc00"   # yellow
    return "#34c759"       # green


def dot(pct):
    if pct >= 95:
        return "\U0001F534"  # red
    if pct >= 80:
        return "\U0001F7E0"  # orange
    if pct >= 50:
        return "\U0001F7E1"  # yellow
    return "\U0001F7E2"      # green


def bar(pct, width=10):
    filled = max(0, min(width, round(pct / 100 * width)))
    return "▓" * filled + "░" * (width - filled)


def usd(v):
    return "—" if v is None else f"${v:,.2f}"


def fmt_reset(iso):
    """Reset time in the machine's LOCAL timezone, rounded to the hour (matches the web UI)."""
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        now = datetime.now().astimezone()
        if dt <= now:
            return "resetting…"
        # rolling window lands on :10; the web UI shows the round hour -> round to match
        disp = dt.replace(minute=0, second=0, microsecond=0)
        if disp.date() == now.date():
            return disp.strftime("today %H:%M")
        if disp.date() == (now + timedelta(days=1)).date():
            return disp.strftime("tomorrow %H:%M")
        return f"{EN_DAYS[disp.weekday()]} {disp.strftime('%H:%M')}"
    except Exception:
        return "?"


def util(node):
    if not node:
        return None
    u = node.get("utilization")
    return None if u is None else round(u)


# --------------------------------------------------------------------------- #
def main():
    token, sub = get_creds()
    if not token:
        out("⚪ Claude")
        out("---")
        out("Token not found in Keychain")
        out("Log into Claude Code, then refresh | color=gray")
        out("Refresh | refresh=true")
        return

    d, stale = get_usage(token)
    if d is None:
        out("\U0001F7E1 Claude")
        out("---")
        out(f"No usage data ({stale}) | color=gray")
        if stale and stale.startswith("HTTP 4"):
            out("Token expired — open Claude Code to refresh it | color=gray")
        out("Retry | refresh=true")
        return

    fh = d.get("five_hour") or {}
    sd = d.get("seven_day") or {}
    so = d.get("seven_day_sonnet") or {}
    op = d.get("seven_day_opus") or {}

    fh_p = util(fh) or 0
    sd_p = util(sd) or 0
    so_p = util(so)
    op_p = util(op)
    worst = max(fh_p, sd_p)

    # ----- Menu bar: dot (worst of the two) + the 5h % -----
    out(f"{dot(worst)} {fh_p}% | size=13")

    # ----- Dropdown -----
    out("---")
    out(f"Claude · {(sub or 'subscription').capitalize()} | color=gray")
    if stale:
        out(f"⏳ cached value (API: {stale}) | size=11 color=gray")
    out("---")
    out(f"5h (session)  {fh_p}% | color={color(fh_p)}")
    out(f"{bar(fh_p)} | font=Menlo size=12 color={color(fh_p)}")
    out(f"↻ resets {fmt_reset(fh.get('resets_at'))} | size=11 color=gray")
    out("---")
    out(f"Weekly (all)  {sd_p}% | color={color(sd_p)}")
    out(f"{bar(sd_p)} | font=Menlo size=12 color={color(sd_p)}")
    out(f"↻ resets {fmt_reset(sd.get('resets_at'))} | size=11 color=gray")
    if so_p is not None or op_p is not None:
        out("---")
        if op_p is not None:
            out(f"Weekly Opus   {op_p}% | color={color(op_p)} size=12")
        if so_p is not None:
            out(f"Weekly Sonnet {so_p}% | color={color(so_p)} size=12")

    # ----- API spend (ccusage) -----
    costs = get_costs()
    out("---")
    out("API spend | color=gray")
    if costs:
        out(f"Today       {usd(costs.get('today'))} | font=Menlo size=12")
        out(f"Last 7 days {usd(costs.get('last7'))} | font=Menlo size=12")
        out(f"This month  {usd(costs.get('month'))} | font=Menlo size=12")
        out(f"Lifetime    {usd(costs.get('lifetime'))} | font=Menlo size=12")
    else:
        out("ccusage not installed | size=11 color=gray")

    out("---")
    # clear caches BEFORE re-running -> forces a live fetch (% and cost) on click
    out("Refresh | bash=/bin/rm param1=-f "
        "param2=" + USAGE_CACHE + " param3=" + COST_CACHE + " terminal=false refresh=true")


if __name__ == "__main__":
    main()
