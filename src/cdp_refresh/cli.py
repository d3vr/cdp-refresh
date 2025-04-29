# src/cdp_refresh/cli.py
"""Command Line Interface definition."""

import typer

app = typer.Typer()


@app.command()
def main(
    watch_path: str = typer.Argument(..., help="Directory path to watch for file changes."),
    cdp_endpoint: str = typer.Option(
        "ws://127.0.0.1:9222",
        "--cdp-endpoint",
        "-c",
        help="Chrome DevTools Protocol endpoint URL.",
    ),
):
    """
    Connects to a running Chrome/Chromium instance via CDP,
    watches a directory for file changes, and reloads a selected tab.
    """
    print(f"Watching path: {watch_path}")
    print(f"Using CDP endpoint: {cdp_endpoint}")
    # TODO: Call core application logic from core.py
    print("Placeholder: Core logic not yet implemented.")


if __name__ == "__main__":
    app()

