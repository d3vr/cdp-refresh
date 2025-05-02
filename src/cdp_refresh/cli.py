"""Command-line interface for CDP refresh."""

import asyncio
import logging
import re
import sys
import traceback
from pathlib import Path
from typing import List, Optional

import typer
from prompt_toolkit import Application
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.prompt import Prompt

from cdp_refresh.core import CDPClient, TabInfo
from cdp_refresh.repl import REPL
from cdp_refresh.watcher import FileWatcher

# Configure logging
logging.basicConfig(
    level=logging.ERROR,  # Default to ERROR level, verbose flag will change to INFO
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
logger = logging.getLogger("cdp_refresh")
console = Console()

# Global debug flag and debugging functions
DEBUG_MODE = False


def debug_html_string(html_string):
    """Debug an HTML string to identify XML parsing issues.

    Args:
        html_string: HTML string to debug
    """
    if not DEBUG_MODE:
        return

    # Simplify debugging - just log the length
    logger.debug(f"HTML content (length: {len(html_string)})")


app = typer.Typer(
    help="CDP Refresh - Watch local files and refresh Chrome tabs",
    add_completion=False,
)


async def _select_tab_fallback(client: CDPClient) -> Optional[TabInfo]:
    """Simple fallback tab selection method without prompt_toolkit.

    Args:
        client: CDP client

    Returns:
        Selected tab or None
    """
    try:
        tabs = await client.get_tabs()

        if not tabs:
            logger.error(
                "No Chrome tabs available. Make sure Chrome is running with pages open."
            )
            return None

        # Print tab list
        console.print(Panel("Available Chrome tabs:", style="bold green"))
        for i, tab in enumerate(tabs):
            title = tab.title[:50] + "..." if len(tab.title) > 50 else tab.title
            console.print(f"[bold cyan]{i + 1}.[/] {title}")
            console.print(f"    [dim]{tab.url}[/]")

        # Get user selection
        choice = Prompt.ask(
            "Select a tab to refresh",
            choices=[str(i + 1) for i in range(len(tabs))],
            show_choices=False,
        )

        return tabs[int(choice) - 1]
    except Exception as e:
        logger.error(f"Error selecting tab with fallback method: {e}")
        return None


async def _select_tab(client: CDPClient) -> Optional[TabInfo]:
    """Prompt user to select a Chrome tab using arrow keys.
    If prompt_toolkit fails, falls back to simple selection.

    Args:
        client: CDP client

    Returns:
        Selected tab or None if no tabs available or selection cancelled
    """
    try:
        # Try to get tabs with better error handling
        try:
            tabs = await client.get_tabs()
        except Exception as e:
            if DEBUG_MODE:
                logger.debug(f"Stack trace: {traceback.format_exc()}")
            logger.error(f"Failed to get Chrome tabs: {e}")
            logger.error(
                "Make sure Chrome is running with remote debugging enabled (--remote-debugging-port=9222)"
            )
            return None

        if not tabs:
            logger.error(
                "No Chrome tabs available. Make sure Chrome is running with pages open."
            )
            return None

        # Debug tab titles
        if DEBUG_MODE:
            logger.debug(f"Found {len(tabs)} tabs:")
            for i, tab in enumerate(tabs):
                logger.debug(
                    f"Tab {i + 1}: title={repr(tab.title)}, url={repr(tab.url)[:50]}..."
                )

        # Setup for arrow key selection
        selected_index = 0
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            nonlocal selected_index
            if selected_index > 0:
                selected_index -= 1
            _update_display()

        @kb.add("down")
        def _(event):
            nonlocal selected_index
            if selected_index < len(tabs) - 1:
                selected_index += 1
            _update_display()

        @kb.add("enter")
        def _(event):
            event.app.exit()

        @kb.add("c-c")
        @kb.add("escape")
        def _(event):
            nonlocal selected_index
            selected_index = -1  # Signal cancellation
            event.app.exit()

        def _get_tab_display() -> str:
            """Generate HTML for tab display with selection highlight."""
            lines = ["<b>Available Chrome tabs (use arrow keys to navigate):</b>\n"]

            for i, tab in enumerate(tabs):
                try:
                    # Ensure we're working with strings and handle potential None values
                    tab_title = str(tab.title) if tab.title else "Untitled"
                    tab_url = str(tab.url) if tab.url else ""

                    # Sanitize and simplify titles to avoid HTML/XML parsing issues
                    # Only keep alphanumeric characters, spaces, and basic punctuation

                    # More aggressive sanitization for HTML/XML parsing
                    # First remove all non-printable characters
                    title = "".join(c for c in tab_title if c.isprintable())

                    # Then remove any HTML special chars
                    title = re.sub(r"[<>&]", "", title)

                    # Finally limit to a very safe subset of characters
                    title = re.sub(r"[^\w\s.,;:!?()\[\]-]", "", title)

                    # Truncate long titles
                    title = title[:50] + "..." if len(title) > 50 else title

                    # No need for character-by-character debugging anymore

                    # Similar aggressive sanitization for URLs
                    # First remove all non-printable characters
                    url_clean = "".join(c for c in tab_url if c.isprintable())

                    # Then remove any HTML special chars
                    url_clean = re.sub(r"[<>&]", "", url_clean)

                    # Keep only URL-safe characters
                    url_simple = re.sub(r"[^\w\s./:?&=\-_~%+]", "", url_clean)

                    # Truncate long URLs
                    url_display = (
                        url_simple[:70] + "..." if len(url_simple) > 70 else url_simple
                    )

                    if i == selected_index:
                        # Highlight selected tab
                        selected_line = f"<b>[→] <ansiblue>{i + 1}.</ansiblue> <ansiyellow>{title}</ansiyellow></b>"
                        url_line = (
                            f"    <ansibrightblack>{url_display}</ansibrightblack>"
                        )

                        # No need for line-by-line HTML debugging anymore

                        lines.append(selected_line)
                        lines.append(url_line)
                    else:
                        normal_line = f"    <ansiblue>{i + 1}.</ansiblue> {title}"
                        url_line = (
                            f"    <ansibrightblack>{url_display}</ansibrightblack>"
                        )
                        lines.append(normal_line)
                        lines.append(url_line)
                except Exception as tab_error:
                    # Handle any errors with a single tab
                    if DEBUG_MODE:
                        logger.warning(f"Error formatting tab {i}: {tab_error}")
                    # Add safe fallback display
                    if i == selected_index:
                        lines.append(
                            f"<b>[→] <ansiblue>{i + 1}.</ansiblue> <ansiyellow>Tab {i + 1}</ansiyellow></b>"
                        )
                    else:
                        lines.append(f"    <ansiblue>{i + 1}.</ansiblue> Tab {i + 1}")

            return "\n".join(lines)

        # Get the HTML string and debug it
        html_string = _get_tab_display()
        if DEBUG_MODE:
            debug_html_string(html_string)

        # Create the control with initial display
        control = FormattedTextControl(HTML(html_string))

        # Function to update display when selection changes
        def _update_display():
            new_html = _get_tab_display()
            if DEBUG_MODE:
                debug_html_string(new_html)

            try:
                control.text = HTML(new_html)
            except Exception as e:
                if DEBUG_MODE:
                    logger.error(f"Error updating display: {e}")

        # Create app layout
        layout = Layout(Window(content=control))

        # Define styles
        style = Style.from_dict(
            {
                "": "bg:#202020 #ffffff",
            }
        )

        # Create and run application
        app = Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            full_screen=False,
            mouse_support=True,
        )

        # Display initial tabs
        console.print(Panel("Loading Chrome tabs...", style="bold green"))

        # Small delay to ensure everything is initialized properly
        await asyncio.sleep(0.2)

        # Run app
        await asyncio.create_task(app.run_async())

        # Handle selection
        if selected_index == -1 or selected_index >= len(tabs):
            return None

        selected_tab = tabs[selected_index]
        console.print(f"Selected: [bold cyan]{selected_tab.title}[/]")

        return selected_tab
    except Exception as e:
        # Get detailed error info

        if DEBUG_MODE:
            error_details = traceback.format_exc()
            logger.error(f"Error with interactive tab selection: {e}")
            logger.debug(f"Stack trace: {error_details}")
        else:
            logger.error(f"Error with interactive tab selection: {e}")

        logger.debug("Falling back to simple tab selection...")

        # Fall back to the simpler selection method
        return await _select_tab_fallback(client)


@app.command()
def watch(
    path: Path = typer.Argument(
        ".",
        help="Directory to watch for changes",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    host: str = typer.Option(
        "localhost",
        "--host",
        "-h",
        help="Chrome host",
    ),
    port: int = typer.Option(
        9222,
        "--port",
        "-p",
        help="Chrome debugging port",
    ),
    ignore: List[str] = typer.Option(
        [],
        "--ignore",
        "-i",
        help="Ignore pattern (can be used multiple times)",
    ),
    no_git_ignore: bool = typer.Option(
        False,
        "--no-git-ignore",
        help="Disable using .gitignore patterns",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug mode with detailed error information",
    ),
) -> None:
    """Watch directory and refresh Chrome tab when files change."""
    # Set log level based on verbose flag
    if verbose:
        logging.getLogger("cdp_refresh").setLevel(logging.INFO)
    else:
        logging.getLogger("cdp_refresh").setLevel(logging.ERROR)

    # Enable debug mode globally
    if debug:
        globals()["DEBUG_MODE"] = True
    else:
        globals()["DEBUG_MODE"] = False

    async def async_main() -> None:
        try:
            # Connect to Chrome
            client = CDPClient(host=host, port=port)

            # Select tab
            tab = await _select_tab(client)
            if not tab:
                return

            # Connect to tab, passing the tab info
            await client.connect(tab.websocket_url, tab=tab)

            # Create REPL first so we can use its file change handler
            repl = REPL(client, watcher=None)  # We'll set the watcher later

            # Setup file watcher with REPL's file change handler
            # Note: handle_file_change now expects a list of changed files
            watcher = FileWatcher(
                path,
                repl.handle_file_change,
                ignore_patterns=ignore,
                use_git_ignore=not no_git_ignore,
            )

            # Now set the watcher in the REPL
            repl.watcher = watcher

            # Prepare ignore status message
            ignore_message = ""
            if ignore:
                ignore_message = f"Ignoring: [cyan]{', '.join(ignore)}[/]\n"

            # Prepare gitignore status
            gitignore_status = "enabled" if not no_git_ignore else "disabled"
            gitignore_message = f"GitIgnore: [cyan]{gitignore_status}[/]\n"

            # Show start message
            console.print(
                Panel.fit(
                    f"[bold green]CDP Refresh is running![/]\n"
                    f"Watching: [cyan]{path}[/]\n"
                    f"Tab: [cyan]{tab.title}[/]\n"
                    f"{ignore_message}"
                    f"{gitignore_message}"
                    f"Type [bold]help[/] for available commands",
                    title="CDP Refresh",
                    border_style="green",
                )
            )

            # Start REPL and watcher with proper error handling
            # repl is already created above
            repl_task = asyncio.create_task(repl.start())
            watcher_task = asyncio.create_task(watcher.start())

            # Create done callback to handle task completion or cancellation
            def task_done(task):
                try:
                    if not task.cancelled() and task.exception():
                        logger.error(f"Task failed with exception: {task.exception()}")
                except Exception:
                    # Ignore any errors in the callback itself
                    pass

            repl_task.add_done_callback(task_done)
            watcher_task.add_done_callback(task_done)

            # Instead of trying to use asyncio.wait() which can lead to cancellation issues,
            # use a simpler approach: just await the REPL task directly
            try:
                # The REPL task will complete when the user chooses to exit
                await repl_task

                # Once REPL is done, cancel the watcher task and clean up
                logger.debug("REPL task completed, cancelling watcher task")
                watcher_task.cancel()

                # No need to wait for it explicitly - the finally block will handle cleanup
            except asyncio.CancelledError:
                # If we're cancelled (e.g., by Ctrl+C), just propagate
                logger.debug("Main task cancelled")
                raise

        except KeyboardInterrupt:
            console.print("[yellow]Interrupted by user[/]")
        except SystemExit:
            # Let sys.exit pass through without additional handling
            raise
        except Exception as e:
            logger.error(f"Error: {e}")
            sys.exit(1)
        finally:
            # Cleanup
            try:
                if "client" in locals():
                    await client.disconnect()
            except Exception:
                # Ignore any errors during cleanup
                pass

    # Run async main
    asyncio.run(async_main())


if __name__ == "__main__":
    app()
