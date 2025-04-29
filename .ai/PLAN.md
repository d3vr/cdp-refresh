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

**Phase 2: Core Browser Interaction (`browser.py`)**

6.  [X] **Implement CDP Connection:**
    *   [X] Create an async function `connect_to_browser(cdp_url)` that uses `playwright.chromium.connect_over_cdp()`. (Implemented within `BrowserManager.connect`)
    *   [X] Handle potential connection errors gracefully (e.g., `playwright._impl._api_types.Error`).
7.  [X] **Implement Tab Listing:**
    *   [X] Create an async function `get_available_pages(browser)` that retrieves all open pages/tabs (`browser.contexts()[0].pages`). (Implemented as `BrowserManager.list_pages`)
    *   [X] Format the output nicely (e.g., index, title, URL). (Formatting will be done in REPL/UI layer)
8.  [X] **Implement Target Page Selection:**
    *   [X] Store the selected `Page` object. (Stored in `BrowserManager._target_page`)
    *   [X] Create a function `set_target_page(page)`. (Implemented as `BrowserManager.set_target_page` and `set_target_page_by_index`)
9.  [X] **Implement Page Reload:**
    *   [X] Create an async function `reload_target_page(page)` that calls `page.reload()`. (Implemented as `BrowserManager.reload_target_page`)
    *   [X] Add error handling (e.g., if the page was closed).

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

**Phase 5: REPL Implementation (`repl.py`)**

15. [ ] **Setup Async REPL:**
    *   [ ] Create an async function `run_repl(browser_manager)` (where `browser_manager` is an object or module providing access to browser functions like listing/selecting tabs).
    *   [ ] Use `prompt_toolkit.PromptSession().prompt_async("> ")` in an async loop.
16. [X] **Implement `choose-tab` Command:**
    *   [X] If input is `choose-tab`:
        *   [X] Call the tab listing function from `browser.py`.
        *   [X] Prompt the user to select a tab by index.
        *   [X] Validate input.
        *   [X] Call the target page selection function from `browser.py` with the chosen page.
17. [X] **Implement `exit` Command:**
    *   [X] If input is `exit`, break the REPL loop or signal shutdown. (Already implemented in `run_repl`)
18. [X] **Handle Unknown Commands:**
    *   [X] Print an informative message for unrecognized input. (Already implemented in `run_repl`)

**Phase 6: Orchestration & Integration (`core.py`)**

19. [X] **Create Core Application Class/Module:**
    *   [X] Design a structure (e.g., an `App` class or functions in `core.py`) to hold state (connected browser, target page, watch path). (Created `App` class in `core.py`)
20. [ ] **Implement Main Async Function:**
    *   [ ] Create `async def run_app(watch_path, cdp_endpoint)`:
        *   [ ] Connect to the browser (`browser.py`). Exit if connection fails.
        *   [ ] Perform initial tab selection (call `repl.py`'s logic or a dedicated initial selection function). Exit if no tab selected.
        *   [ ] Define the reload callback function (which calls `browser.reload_target_page`).
        *   [ ] Create and run the file watcher task (`watcher.py`) using `asyncio.create_task`.
        *   [ ] Create and run the REPL task (`repl.py`) using `asyncio.create_task`.
        *   [ ] Use `asyncio.gather` or similar to run tasks concurrently and wait for completion/cancellation.
21. [ ] **Integrate with CLI (`cli.py`):**
    *   [ ] Modify the `typer` function in `cli.py` to call `core.run_app` with the parsed arguments. Use `asyncio.run()`.
22. [ ] **Implement Graceful Shutdown:**
    *   [ ] Handle `KeyboardInterrupt` and the `exit` command.
    *   [ ] Ensure `asyncio` tasks are cancelled.
    *   [ ] Close the Playwright browser connection (`browser.close()`).

**Phase 7: Refinement & Testing**

23. [ ] **Manual Testing:**
    *   [ ] Launch Chrome with remote debugging.
    *   [ ] Run the tool, select a tab.
    *   [ ] Modify a file in the watched directory. Verify the tab reloads.
    *   [ ] Use the `choose-tab` command to select a different tab. Verify reload works on the new tab.
    *   [ ] Use the `exit` command. Verify clean shutdown.
    *   [ ] Test edge cases (invalid path, browser closed, invalid CDP endpoint).
24. [ ] **Error Handling Review:**
    *   [ ] Ensure user-friendly error messages for common issues (connection failure, invalid input).
25. [ ] **README Update:**
    *   [ ] Finalize installation and usage instructions (including `uv`).
    *   [ ] Add examples.
    *   [ ] Document REPL commands.

