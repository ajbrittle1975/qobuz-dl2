# ConPort Memory Export

Exported from `context_portal/context.db` on 2026-06-13.

This is the full contents of the ConPort (Context Portal) memory that this project
previously used. The `product_context` and `active_context` tables were empty (`{}`),
and there were no `progress_entries`, `system_patterns`, `custom_data`, or
`context_links` rows. The only substantive content is the **decision log** below.

The Roo Code `memory-bank/*.md` files were uninitialized templates (no real content).

---

## Decisions

### 1. Adopt uv with PEP 621 pyproject.toml; target Python >=3.9; preserve existing console scripts
*2025-10-20 — tags: packaging, uv, pep621, python39, console-scripts*

**Rationale:** uv provides fast, deterministic dependency management and modern
workflows; PEP 621 centralizes metadata; Python 3.9+ enables typing and stdlib
features used in refactors; keeping scripts ensures zero UX break initially.

**Implementation:** Create pyproject.toml with `[build-system]=hatchling`, `[project]`
metadata, `[project.scripts]` `qobuz-dl` and `qdl` -> `qobuz_dl:main`; migrate
requirements.txt into `[project.dependencies]`; generate uv.lock; deprecate setup.py
after verification.

### 2. Migrate CLI from argparse to Click with command groups
*2025-10-20 — tags: cli, click, ux*

**Rationale:** Click improves UX (rich help, prompts), structure (groups/subcommands),
and testability; aligns with modern CLI standards.

**Implementation:** Refactor `qobuz_dl/commands.py` and `qobuz_dl/cli.py` to Click
groups: root with options (`--reset`, `--purge`, `--show-config`); subcommands `fun`,
`dl`, `lucky`; maintain flag compatibility; add auto-completion.

### 3. Refactor HTTP and download pipeline to asyncio + httpx for concurrency
*2025-10-20 — tags: async, httpx, performance, streaming*

**Rationale:** Concurrent downloads with `httpx.AsyncClient` and streaming improves
throughput and responsiveness versus synchronous requests.

**Implementation:** Replace requests/tqdm in downloader with httpx streaming, bounded
semaphore concurrency, timeouts; staged migration: keep requests in qopy until API
calls are adapted, then migrate sequentially.

### 4. Introduce reliability primitives: retries and backoff
*2025-10-20 — tags: reliability, retries, tenacity, backoff*

**Rationale:** Network instability and CDN hiccups require robust retry policies to
reduce failures and partial downloads.

**Implementation:** Use tenacity (or backoff) for exponential backoff on transient HTTP
and tagging operations; centralize retry policy and classify retryable exceptions.

### 5. Adopt rich for progress and console UX with non-TTY fallback
*2025-10-20 — tags: ux, rich, progress*

**Rationale:** rich provides high-quality progress bars and structured console output
beyond tqdm; improves clarity during multi-download operations.

**Implementation:** Replace tqdm with rich progress; add TTY detection fallback to
minimal logs; ensure quiet/CI-friendly output mode.

### 6. Enable code quality toolchain: ruff, mypy, pytest
*2025-10-20 — tags: quality, linting, typing, testing, ruff, mypy, pytest*

**Rationale:** Static analysis and tests improve maintainability and prevent
regressions during refactor.

**Implementation:** Configure `[tool.ruff]`, `[tool.mypy]`, and pytest in
pyproject.toml; add type hints across modules; add minimal smoke tests for CLI and
downloader; wire with `uv run`.
