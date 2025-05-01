# PLAN.md - CDP Refresh Tool Development Plan

This document outlines the steps to build the CDP Refresh tool, which monitors file changes and reloads a selected Chrome tab via the Chrome DevTools Protocol (CDP) using Playwright. We will use `uv` for virtual environment and package management.

**Phase 1: Project Setup & Core Dependencies**

1.  [X] **Initialize Project Structure:**
    *   [X] Create `src/cdp_refresh/` directory.
    *   [X] Create `src/cdp_refresh/__init__.py`.
    *   [X] Create placeholder files: `src/cdp_refresh/cli.py`, `src/cdp_refresh/browser.py`, `src/cdp_refresh/watcher.py`, `src/cdp_refresh/repl.py`, `src/cdp_refresh/core.py`.
2.  [X] **Update `pyproject.toml`:**
    *   [X] Add `playwright`, `watchfiles`, `prompt_toolkit`, `typer[all]` to `[project.dependencies]`.
    *   [X] Configure project entry points if using `typer` or for `python -m`.
3.  [X] **Install Dependencies (using `uv`):**
    *   [X] Create a virtual environment (e.g., `uv venv`).
    *   [X] Activate the virtual environment.
    *   [X] Install the project in editable mode and its dependencies: `uv pip install -e .` (or `uv sync` if generating lock files).
    *   [X] Run `playwright install chromium` (or just `playwright install` if needed).
4.  [X] **Update `.gitignore`:**
    *   [X] Add common Python ignores (`__pycache__`, virtual environment folders like `.venv`, build artifacts like `dist/`, `*.egg-info/`). Ensure `.venv` (or your chosen venv name) is included.
5.  [X] **Update `README.md`:**
    *   [X] Add basic project description.
    *   [X] Add **critical** instructions on how to launch Chrome/Chromium with the remote debugging port enabled (e.g., `google-chrome --remote-debugging-port=9222`).
    *   [X] Add installation instructions using `uv` (creating venv, installing dependencies).

**Phase 2: Core Browser Interaction (`browser.py`)** (Revised Approach)

6.  [X] **Implement CDP Connection (to specific page):**
    *   [X] `BrowserManager`'s `connect` method now accepts a page-specific `webSocketDebuggerUrl`.
    *   [X] Uses `playwright.chromium.connect_over_cdp()` to connect to the single target page.
    *   [X] Handles potential connection errors.
7.  [ ] **Implement Tab Listing (Revised):**
    *   [ ] `BrowserManager.list_pages` now only lists the single connected page (if successful). (Marking incomplete as behavior changed significantly)
8.  [ ] **Implement Target Page Selection (Revised):**
    *   [ ] Selection now happens *before* connection in `core.py` using HTTP `/json/list` endpoint.
    *   [ ] `BrowserManager` no longer needs `set_target_page` methods. (Marking incomplete as responsibility moved)
9.  [X] **Implement Page Reload (Revised):**
    *   [X] `BrowserManager.reload_target_page` now reloads the single connected page obtained from `browser.contexts[0].pages[0]`.
    *   [X] Add error handling (e.g., if the page was closed, timeout).

**Phase 3: Command Line Interface & Entry Point (`cli.py`, `__main__.py`)**

10. [X] **Define CLI Arguments (`cli.py`):**
    *   [X] Use `typer` to create a main CLI function.
    *   [X] Add an argument for the `watch_path` (directory to monitor).
    *   [X] Add an optional argument for the `cdp_endpoint` (defaulting to `ws://127.0.0.1:9222`).
11. [X] **Basic Application Runner (`cli.py`):**
    *   [X] In the main `typer` function, call the core application logic (which will eventually reside in `core.py`). For now, it can just print the arguments.
12. [X] **Create Module Entry Point (`__main__.py`):**
    *   [X] Create `src/cdp_refresh/__main__.py`.
    *   [X] Import and run the `typer` app from `cli.py`. This allows running via `python -m cdp_refresh`.
13. [X] **Configure `pyproject.toml` Entry Point:**
    *   [X] Add `[project.scripts]` section in `pyproject.toml` to create a console script (e.g., `cdp-refresh = "cdp_refresh.cli:app"` if using Typer's default app name).

**Phase 4: File Watching (`watcher.py`)**

14. [X] **Implement Async Watcher:**
    *   [X] Create an async function `watch_directory(path, callback)`.
    *   [X] Use `watchfiles.awatch` to monitor the `path`.
    *   [X] On detecting changes, call the provided async `callback` function.
    *   [X] Ensure it handles different change types appropriately (any change triggers reload).

**Phase 5: REPL Implementation (`repl.py`)** (Revised)

15. [X] **Setup Async REPL:**
    *   [X] Create an async function `run_repl(browser_manager, shutdown_callback)`.
    *   [X] Use `prompt_toolkit.PromptSession().prompt_async("> ")` in an async loop.
16. [ ] **Implement `choose-tab` Command (Removed):**
    *   [ ] Command removed as connection is now page-specific. (Marking incomplete as feature removed)
17. [X] **Implement `exit` Command:**
    *   [X] If input is `exit`, signal shutdown and break loop.
18. [X] **Handle Unknown Commands:**
    *   [X] Print an informative message for unrecognized input.

**Phase 6: Orchestration & Integration (`core.py`)**

19. [X] **Create Core Application Class/Module:**
    *   [X] Design a structure (e.g., an `App` class or functions in `core.py`) to hold state (watch path, CDP port, connected page via BrowserManager).
20. [X] **Implement Main Async Function (Revised):**
    *   [X] Create `async def run_app(watch_path, cdp_port)`:
        *   [X] Fetch available page targets via HTTP (`_get_page_targets`). Exit if none found.
        *   [X] Prompt user to select a target page (`_initial_tab_selection`). Exit if cancelled.
        *   [X] Connect `BrowserManager` directly to the selected page's `webSocketDebuggerUrl`. Exit if connection fails.
        *   [X] Define the reload callback function (which calls `browser_manager.reload_target_page`).
        *   [X] Create and run the file watcher task (`watcher.py`).
        *   [X] Create and run the REPL task (`repl.py`).
        *   [X] Wait for shutdown signal (`_shutdown_event.wait()`).
21. [X] **Integrate with CLI (`cli.py`):**
    *   [X] Modify the `typer` function in `cli.py` to call `core.run_app` with the parsed arguments. Use `asyncio.run()`. (Implemented in `cli.py`)
22. [X] **Implement Graceful Shutdown:**
    *   [X] Handle `KeyboardInterrupt` and the `exit` command. (Handled via `shutdown_callback` in REPL, `_shutdown_event` in core, and `try/except` in `cli.py`)
    *   [X] Ensure `asyncio` tasks are cancelled. (Implemented in `App.shutdown` and `App._cleanup_tasks`)
    *   [X] Close the Playwright browser connection (`browser.close()`). (Implemented in `BrowserManager.disconnect`, called by `App.shutdown`)

**Phase 7: Refinement & Testing**

23. [X] **Manual Testing:**
    *   [X] Launch Chrome with remote debugging.
    *   [X] Run the tool, select a tab.
    *   [X] Modify a file in the watched directory. Verify the tab reloads.
    *   [X] Use the `choose-tab` command to select a different tab. Verify reload works on the new tab.
    *   [X] Use the `exit` command. Verify clean shutdown.
    *   [X] Test edge cases (invalid path, browser closed, invalid CDP endpoint). (Performed manually)
24. [ ] **Error Handling Review:**
    *   [ ] Ensure user-friendly error messages for common issues (connection failure, invalid input).
25. [ ] **README Update:**
    *   [ ] Finalize installation and usage instructions (including `uv`).
    *   [ ] Add examples.
    *   [ ] Document REPL commands.

