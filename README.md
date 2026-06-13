# qobuz-dl (modernized fork) · v2.0.0

Search, explore, and download Lossless and Hi-Res music from [Qobuz](https://www.qobuz.com/).

> **This is a community fork.** It is a modernized, async rewrite of the original
> [`qobuz-dl` by vitiko98](https://github.com/vitiko98/qobuz-dl), which is no
> longer maintained. All credit for the original tool, the Qobuz API wrapper
> (`qopy`, originally by **Sorrow446**), and the app-secret extraction
> (`spoofbuz`, based on **DashLt**'s work) goes to those authors. This fork is
> free and open source under the **GNU GPL v3** and focuses on getting the tool
> *working again* on today's Qobuz, plus a broad code-quality overhaul.

---

## Why this fork exists

In 2024–2025 Qobuz **removed the direct email/password login API** and moved
authentication behind an OAuth flow protected by reCAPTCHA. The original
`qobuz-dl` (unmaintained since ~2022) logged in with email + password and simply
stopped working — every run failed at login.

**This fork fixes that** by authenticating with a `user_auth_token` taken from a
logged-in browser session instead of a password. You no longer log in from
Python at all; you reuse the session your browser already established.

The token is a short-lived JWT, so the fork also:

- **Auto-refreshes** the token on every run (via the Qobuz `partner` endpoint)
  and writes the fresh token back to your config — so as long as you run the
  tool periodically, you rarely need to touch it again.
- Ships a **browser login helper** (`qobuz-dl2 login`) that captures the token
  for you, and a **`qobuz-dl2 set-token`** command for pasting one manually.

## Features

- **Token-based auth** that works with current Qobuz, with automatic refresh.
- **Fast, concurrent downloads** via an async `httpx` architecture.
- **Resilient networking**: transient download failures retry with exponential
  backoff (`tenacity`) at the network level.
- **Modern CLI** built on `Click` with `rich` progress bars.
- **Download modes**: `dl` (by URL/text file), `fun` (interactive), `lucky`
  (top search result).
- **Smart extras**: multi-disc albums, M3U playlist generation, extended FLAC/MP3
  tagging, cover art embedding, duplicate-download database, and an artist
  "smart discography" filter.

## Requirements

- An **active Qobuz subscription** (free accounts cannot download).
- Python ≥ 3.9.

## Installation

This fork is installed **from source** (it is intentionally not published to
PyPI under the original `qobuz-dl` name). Clone the repo, then install with
[uv](https://docs.astral.sh/uv/) from the project directory:

```bash
git clone <your-fork-url> qobuz-dl2
cd qobuz-dl2

# Core tool — exposes the `qobuz-dl2` command
uv tool install .

# Optional: enable the browser login helper (qobuz-dl2 login)
uv tool install --force ".[browser]"
python -m playwright install chromium   # one-time browser download
```

On first run the tool creates a config file and asks for your token. You can
leave it blank and capture it automatically afterward with `qobuz-dl2 login`.

## Getting your token

Pick whichever is easiest:

### Option A — automatic (recommended)

```bash
qobuz-dl2 login
```

A browser window opens. **Log in to Qobuz normally** (type your password, solve
any captcha — you do it, not a script). The window closes and your token is
saved automatically. Requires the `[browser]` extra above.

### Option B — paste it manually

1. Log in at <https://play.qobuz.com>.
2. Open **DevTools → Network**, filter by `login`.
3. Click the `user/login` request → **Response** tab.
4. Copy the value of `user_auth_token`.
5. Store it:

   ```bash
   qobuz-dl2 set-token "PASTE_TOKEN_HERE"
   ```

If your token ever fully expires, the tool tells you exactly what to do; just
re-run `qobuz-dl2 login` (or `set-token`).

## Usage

```bash
# Download by URL (album, track, artist, label, playlist, or a last.fm playlist)
qobuz-dl2 dl https://open.qobuz.com/album/xxxxxxxxxxxxx

# Download several at once, or from a text file of URLs
qobuz-dl2 dl urls.txt https://open.qobuz.com/track/123456

# Interactive search-and-pick
qobuz-dl2 fun

# Grab the top search result
qobuz-dl2 lucky "miles davis kind of blue"
```

### Quality levels

| ID | Quality                  |
|----|--------------------------|
| 5  | MP3 320                  |
| 6  | 16-bit / 44.1 kHz (CD)   |
| 7  | 24-bit / ≤ 96 kHz        |
| 27 | 24-bit / > 96 kHz        |

```bash
qobuz-dl2 dl -q 27 <url>          # request best Hi-Res
qobuz-dl2 dl --no-fallback -q 27  # skip releases not available at that quality
```

Run `qobuz-dl2 <command> --help` for the full option list (directory, naming
formats, cover art, database, smart discography, etc.).

## Configuration

Config lives at:

- Linux/macOS: `~/.config/qobuz-dl/config.ini`
- Windows: `%APPDATA%\qobuz-dl\config.ini`

`qobuz-dl2 -r` recreates it, `qobuz-dl2 -sc` prints it, and `qobuz-dl2 -p` purges the
downloaded-IDs database. Your `user_auth_token` is stored (in the historical
`password` field) **in plain text** — protect this file accordingly.

## Development

```bash
uv sync                 # install dev dependencies
uv run pytest           # run the test suite
uv run ruff check .     # lint
uv run mypy qobuz_dl2   # type-check
```

## What changed in this fork (v2.0.0)

- **Auth:** replaced dead email/password login with `user_auth_token` auth +
  automatic refresh and config write-back; added `login` and `set-token`.
- **Bug fixes:** corrected a broken color f-string, an unhandled invalid-URL
  error, an over-eager album-level retry that re-downloaded whole albums, a
  filename-truncation bug that could mangle paths, a `KeyError` on missing MP3
  copyright, a crash in `smart_discography`, and a swapped ℗/© copyright symbol.
- **Robustness:** request timeouts, hardened secret extraction, graceful auth
  errors, and proper HTTP-client cleanup.
- **Maintainability:** de-duplicated the CLI commands, removed dead code,
  dropped the `colorama` dependency, and added a `pytest` smoke suite.

## Credits

- This modernized fork is maintained by **4themusic**.
- Original **qobuz-dl** by [vitiko98](https://github.com/vitiko98/qobuz-dl).
- `qopy` Qobuz API wrapper originally by **Sorrow446**.
- `spoofbuz` app-secret logic based on **DashLt**'s work.

## License

Free and open source under the **GNU General Public License v3.0 or later**
(GPL-3.0-or-later). See [LICENSE](LICENSE) for the full text. You are free to
use, study, share, and modify it; derivative works must remain under the same
license.

This tool is intended for downloading music you are entitled to through your own
Qobuz subscription.
