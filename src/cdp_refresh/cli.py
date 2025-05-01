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
        
        # Import prompt_toolkit components for tab selection UI
        try:
            from prompt_toolkit import Application
            from prompt_toolkit.formatted_text import HTML
            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.layout.containers import Window
            from prompt_toolkit.layout.controls import FormattedTextControl
            from prompt_toolkit.layout import Layout
            from prompt_toolkit.styles import Style
        except ImportError as e:
            logger.error(f"Error importing prompt_toolkit: {e}")
            logger.error("Make sure prompt_toolkit is installed correctly")
            logger.error("Try: pip install prompt_toolkit>=3.0.38")
            return None
        
        # Setup for arrow key selection
        selected_index = 0
        kb = KeyBindings()
        
        @kb.add('up')
        def _(event):
            nonlocal selected_index
            if selected_index > 0:
                selected_index -= 1
            _update_display()
        
        @kb.add('down')
        def _(event):
            nonlocal selected_index
            if selected_index < len(tabs) - 1:
                selected_index += 1
            _update_display()
        
        @kb.add('enter')
        def _(event):
            event.app.exit()
        
        @kb.add('c-c')
        @kb.add('escape')
        def _(event):
            nonlocal selected_index
            selected_index = -1  # Signal cancellation
            event.app.exit()
        
        def _get_tab_display() -> str:
            """Generate HTML for tab display with selection highlight."""
            lines = ["<b>Available Chrome tabs (use arrow keys to navigate):</b>\n"]
            
            for i, tab in enumerate(tabs):
                # Ensure we're working with strings and handle potential None values
                tab_title = str(tab.title) if tab.title else "Untitled"
                tab_url = str(tab.url) if tab.url else ""
                
                # Truncate long titles/URLs
                title = tab_title[:50] + "..." if len(tab_title) > 50 else tab_title
                url_display = tab_url[:70] + "..." if len(tab_url) > 70 else tab_url
                
                if i == selected_index:
                    # Highlight selected tab
                    lines.append(f"<b>[→] <ansiblue>{i+1}.</ansiblue> <ansiyellow>{title}</ansiyellow></b>")
                    lines.append(f"    <ansibrightblack>{url_display}</ansibrightblack>")
                else:
                    lines.append(f"    <ansiblue>{i+1}.</ansiblue> {title}")
                    lines.append(f"    <ansibrightblack>{url_display}</ansibrightblack>")
            
            return "\n".join(lines)
        
        # Create the control with initial display
        control = FormattedTextControl(HTML(_get_tab_display()))
        
        # Function to update display when selection changes
        def _update_display():
            control.text = HTML(_get_tab_display())
        
        # Create app layout
        layout = Layout(Window(content=control))
        
        # Define styles
        style = Style.from_dict({
            "": "bg:#202020 #ffffff",
        })
        
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
        
        # Run app
        await asyncio.create_task(app.run_async())
        
        # Handle selection
        if selected_index == -1 or selected_index >= len(tabs):
            return None
            
        selected_tab = tabs[selected_index]
        console.print(f"Selected: [bold cyan]{selected_tab.title}[/]")
        
        return selected_tab
    except Exception as e:
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