"""Command-line interface for CDP refresh."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich import box

from cdp_refresh.core import CDPClient, TabInfo
from cdp_refresh.watcher import FileWatcher
from cdp_refresh.repl import REPL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("cdp_refresh")
console = Console()

# Global debug flag
DEBUG_MODE = False

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
            logger.error("No Chrome tabs available. Make sure Chrome is running with pages open.")
            return None
        
        # Print tab list
        console.print(Panel("Available Chrome tabs:", style="bold green"))
        for i, tab in enumerate(tabs):
            title = tab.title[:50] + "..." if len(tab.title) > 50 else tab.title
            console.print(f"[bold cyan]{i+1}.[/] {title}")
            console.print(f"    [dim]{tab.url}[/]")
        
        # Get user selection
        choice = Prompt.ask(
            "Select a tab to refresh",
            choices=[str(i+1) for i in range(len(tabs))],
            show_choices=False
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
                import traceback
                logger.error(f"Detailed error getting tabs: {traceback.format_exc()}")
            logger.error(f"Failed to get Chrome tabs: {e}")
            logger.info("Make sure Chrome is running with remote debugging enabled (--remote-debugging-port=9222)")
            return None
            
        if not tabs:
            logger.error("No Chrome tabs available. Make sure Chrome is running with pages open.")
            return None
        
        # Use a simpler approach instead of HTML-based prompt_toolkit
        # Import Python standard curses library for terminal UI
        try:
            import curses
            import curses.ascii
        except ImportError:
            logger.error("Failed to import curses for interactive selection")
            return await _select_tab_fallback(client)

        # Prepare tab display data
        tab_titles = []
        for tab in tabs:
            # Clean title for display
            title = str(tab.title) if tab.title else "Untitled"
            title = title[:60] + "..." if len(title) > 60 else title
            tab_titles.append(title)
            
        # Define the curses UI wrapper function
        async def _curses_ui():
            selected_idx = 0
            result = None
            
            def _draw_menu(stdscr, selected_idx):
                stdscr.clear()
                h, w = stdscr.getmaxyx()
                
                # Print header
                header = "Available Chrome tabs (use arrow keys to navigate, Enter to select)"
                stdscr.addstr(0, 0, header[:w-1], curses.A_BOLD)
                stdscr.addstr(1, 0, "-" * min(len(header), w-1))
                
                # Calculate visible range for scrolling if needed
                visible_count = h - 4  # Header + separator + instruction
                start_idx = max(0, selected_idx - (visible_count // 2))
                end_idx = min(len(tab_titles), start_idx + visible_count)
                
                # Print tab list
                for i in range(start_idx, end_idx):
                    y = i - start_idx + 2
                    prefix = f"{i+1}. "
                    
                    # Set highlight for selected item
                    if i == selected_idx:
                        attr = curses.A_REVERSE
                        prefix = "→ " + prefix
                    else:
                        attr = curses.A_NORMAL
                        prefix = "  " + prefix
                    
                    # Make sure text fits in the window
                    display_width = w - len(prefix) - 1
                    title_display = tab_titles[i][:display_width]
                    
                    stdscr.addstr(y, 0, prefix + title_display, attr)
                
                # Print footer
                footer = "Press Enter to select, Esc to cancel"
                if h > end_idx - start_idx + 4:
                    stdscr.addstr(h-1, 0, footer[:w-1])
                
                stdscr.refresh()
            
            def _curses_main(stdscr):
                nonlocal selected_idx, result
                
                # Setup terminal
                curses.curs_set(0)  # Hide cursor
                stdscr.timeout(100)  # Non-blocking input with timeout
                
                # Initial display
                _draw_menu(stdscr, selected_idx)
                
                # Main loop
                while True:
                    try:
                        c = stdscr.getch()
                        
                        if c == curses.KEY_UP:
                            selected_idx = max(0, selected_idx - 1)
                        elif c == curses.KEY_DOWN:
                            selected_idx = min(len(tab_titles) - 1, selected_idx + 1)
                        elif c == curses.KEY_ENTER or c == 10 or c == 13:  # Enter key
                            result = selected_idx
                            break
                        elif c == 27:  # Escape key
                            result = None
                            break
                        
                        _draw_menu(stdscr, selected_idx)
                    except Exception as e:
                        # Just in case of terminal errors
                        break
            
            # Run curses in a separate thread to not block the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: curses.wrapper(_curses_main))
            
            return result
        
        # Show initial message
        console.print(Panel("Loading tab selector...", style="bold green"))
        
        # Run the UI and get the selected index
        selected_index = await _curses_ui()
        
        # Check if selection was cancelled
        if selected_index is None or selected_index >= len(tabs):
            logger.info("Tab selection cancelled")
            return None
        
        # Handle selection
        if selected_index == -1 or selected_index >= len(tabs):
            return None
            
        selected_tab = tabs[selected_index]
        console.print(f"Selected: [bold cyan]{selected_tab.title}[/]")
        
        return selected_tab
    except Exception as e:
        # Get detailed error info
        import traceback
        error_details = traceback.format_exc()
        
        if DEBUG_MODE:
            logger.error(f"Detailed error with interactive tab selection:\n{error_details}")
        else:
            logger.error(f"Error with interactive tab selection: {e}")
            
        logger.info("Falling back to simple tab selection...")
        
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
    # Set log level
    if verbose:
        logging.getLogger("cdp_refresh").setLevel(logging.DEBUG)
        
    # Enable debug mode globally
    if debug:
        globals()['DEBUG_MODE'] = True
    else:
        globals()['DEBUG_MODE'] = False
    
    async def async_main() -> None:
        try:
            # Connect to Chrome
            client = CDPClient(host=host, port=port)
            
            # Select tab
            tab = await _select_tab(client)
            if not tab:
                return
            
            # Connect to tab
            await client.connect(tab.websocket_url)
            
            # Setup file watcher
            async def on_change() -> None:
                console.print("[yellow]Files changed, reloading page...[/]")
                await client.reload_page()
            
            watcher = FileWatcher(path, on_change)
            
            # Show start message
            console.print(Panel.fit(
                f"[bold green]CDP Refresh is running![/]\n"
                f"Watching: [cyan]{path}[/]\n"
                f"Tab: [cyan]{tab.title}[/]\n"
                f"Type [bold]help[/] for available commands",
                title="CDP Refresh",
                border_style="green",
            ))
            
            # Start REPL and watcher with proper error handling
            repl = REPL(client, watcher)
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
            
            try:
                # Wait for both tasks to complete or for a keyboard interrupt
                await asyncio.gather(repl_task, watcher_task)
            except asyncio.CancelledError:
                # Propagate cancellation
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
                if 'client' in locals():
                    await client.disconnect()
            except Exception:
                # Ignore any errors during cleanup
                pass
    
    # Run async main
    asyncio.run(async_main())


if __name__ == "__main__":
    app()