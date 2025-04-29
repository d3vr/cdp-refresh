# src/cdp_refresh/cli.py
"""Command Line Interface definition."""

import asyncio
import sys

import typer

from .core import run_app

app = typer.Typer(
    help="""
    Connects to a running Chrome/Chromium instance via CDP,
    watches a directory for file changes, and reloads a selected tab.

    Requires Chrome/Chromium to be launched with the remote debugging port enabled,
    e.g., google-chrome --remote-debugging-port=9222
    """
)


@app.command()
def main(
    watch_path: str = typer.Argument(..., help="Directory path to watch for file changes."),
    cdp_port: int = typer.Option(
        9222,
        "--cdp-port",
        "-p", # Changed short flag
        help="Chrome DevTools Protocol port (assumes host is 127.0.0.1).",
    ),
):
    """
    Connects to a running Chrome/Chromium instance via CDP (on 127.0.0.1),
    watches a directory for file changes, and reloads a selected tab.
    """
    # Basic validation (core.py does more thorough path validation)
    if not watch_path:
        print("Error: Watch path cannot be empty.", file=sys.stderr)
        raise typer.Exit(code=1)

    try:
        # Pass the port directly to the core application logic
        asyncio.run(run_app(watch_path=watch_path, cdp_port=cdp_port))
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        # asyncio.run should handle cleanup of the event loop,
        # and run_app is designed to handle cancellation/shutdown gracefully.
    except Exception as e:
        # Catch unexpected errors at the top level
        print(f"\nAn unexpected error occurred in the CLI: {e}", file=sys.stderr)
        raise typer.Exit(code=1)


# This allows running the script directly for debugging, though using the
# installed console script or `python -m cdp_refresh` is preferred.
if __name__ == "__main__":
    app()

