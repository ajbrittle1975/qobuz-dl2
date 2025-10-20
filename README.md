# qobuz-dl

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=VZWSWVGZGJRMU&source=url)

Search, explore, and download Lossless and Hi-Res music from [Qobuz](https://www.qobuz.com/). This project is a modernized, high-performance fork that *just works*™ (2025).

## Features

- **Fast, Concurrent Downloads**: Utilizes an asynchronous architecture with `httpx` to download multiple tracks in parallel.
- **Resilient Network**: Automatically retries failed downloads with exponential backoff using `tenacity`.
- **Modern CLI**: A beautiful and intuitive command-line interface powered by `Click` and `rich`, complete with progress bars and rich formatting.
- **Robust Package Management**: Uses `uv` for fast, reliable dependency management.
- **Download Modes**:
  - `dl`: Download albums, tracks, artists, playlists, and labels directly by URL.
  - `fun`: Explore and download music interactively.
  - `lucky`: Instantly download the top search result for a query.
- **Duplicate Handling**: Prevents re-downloading tracks with a local database.
- **And more**: Supports multi-disc albums, M3U playlist generation, extended tagging, and URL imports from text files.

## Getting Started

> You'll need an **active Qobuz subscription**.

#### Installation

Install and run globally with `uv`:

```bash
# Install the tool
uv tool install qobuz-dl

# Run it
qobuz-dl --help
```

On your first run, the tool will prompt you to create a configuration file for your email, password, and default settings.

## Usage

The command-line interface is structured into three main commands: `dl`, `fun`, and `lucky`.

```
Usage: qobuz-dl [OPTIONS] COMMAND [ARGS]...

  The ultimate Qobuz music downloader.

Options:
  -r, --reset         Create or reset the configuration file.
  -p, --purge         Purge/delete the downloaded-IDs database.
  -sc, --show-config  Show the current configuration.
  -h, --help          Show this message and exit.

Commands:
  dl     Download by URL for an album, track, artist, playlist, or label.
  fun    Explore and download music interactively.
  lucky  Download the first <n> results for a Qobuz search query.
```

### `dl` Command

Download one or more items directly via their Qobuz URL.

**Download an album in 24-bit / <=96kHz quality:**

```bash
qobuz-dl dl https://play.qobuz.com/album/qxjbxh1dc3xyb -q 7
```

**Download multiple URLs to a custom directory:**

```bash
qobuz-dl dl https://play.qobuz.com/artist/2038380 https://play.qobuz.com/album/ip8qjy1m6dakc -d "My Music"
```

**Download from a text file containing a list of URLs:**

```bash
qobuz-dl dl urls.txt
```

### `fun` Command

Launch an interactive session to search for and select music to download.

**Start interactive mode with a search result limit of 10:**

```bash
qobuz-dl fun -l 10
```

You will be prompted to choose a search type (Albums, Tracks, etc.) and then enter your query. Use the arrow keys and spacebar to select items from the results list.

### `lucky` Command

Download the top search result(s) for a given query without manual selection.

**Download the first album result for "die lit":**

```bash
qobuz-dl lucky playboi carti die lit
```

**Download the top 5 artist results for "joy division":**

```bash
qobuz-dl lucky joy division -n 5 --type artist
```

## For Developers

This project uses `uv` for package management and `hatchling` for builds.

**1. Clone the repository:**

```bash
git clone https://github.com/vitiko98/Qobuz-DL.git
cd Qobuz-DL
```

**2. Create a virtual environment and install dependencies:**

```bash
# Create a virtual environment
uv venv

# Activate it (macOS/Linux)
source .venv/bin/activate

# Install runtime and development dependencies
uv sync -g dev
```

**3. Run the application from source:**

```bash
uv run qobuz-dl --help
```

**4. Run linters and type checkers:**

```bash
# Run ruff linter
uv run ruff check .

# Run mypy type checker
uv run mypy .
```

## Disclaimer

- This tool is for educational purposes only. By using it, you accept the [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf).
- `qobuz-dl` is not affiliated with Qobuz.
