"""Command-line interface for CDP refresh."""

import asyncio
import logging
import os
import sys
import traceback
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

# Global debug flag and debugging functions
DEBUG_MODE = False

def debug_html_string(html_string):
    """Debug an HTML string to identify XML parsing issues.
    
    Args:
        html_string: HTML string to debug
    """
    if not DEBUG_MODE:
        return
        
    print("\n--- HTML DEBUG ---")
    
    # Print with line numbers and character positions
    lines = html_string.split('\n')
    for i, line in enumerate(lines):
        print(f"Line {i+1}:")
        print(line)
        # Print character position markers every 10 chars
        ruler = ' '.join([f"{j:1d}" for j in range(1, 10)]) + ' '
        ruler = ruler * (len(line) // 10 + 1)
        print(ruler[:len(line)])
        print("-" * len(line))
    
    # Also print a character-by-character view with character codes
    print("\nCharacter codes:")
    for i, line in enumerate(lines):
        if i == 5:  # Line 6 (0-indexed) where error reportedly is
            print(f"Line {i+1} (reported error location):")
            for j, char in enumerate(line):
                # Extra detail around the error position
                if j >= 55 and j <= 65:  # Focus on columns 55-65
                    print(f"Col {j+1}: '{char}' (ord={ord(char)}, hex={hex(ord(char))})")
    
    print("--- END DEBUG ---\n")

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
            
        # Debug tab titles
        if DEBUG_MODE:
            logger.info(f"Found {len(tabs)} tabs:")
            for i, tab in enumerate(tabs):
                logger.info(f"Tab {i+1}: title={repr(tab.title)}, url={repr(tab.url)[:50]}...")
        
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
                try:
                    # Ensure we're working with strings and handle potential None values
                    tab_title = str(tab.title) if tab.title else "Untitled"
                    tab_url = str(tab.url) if tab.url else ""
                    
                    # Sanitize and simplify titles to avoid HTML/XML parsing issues
                    # Only keep alphanumeric characters, spaces, and basic punctuation
                    import re
                    
                    # More aggressive sanitization for HTML/XML parsing
                    # First remove all non-printable characters
                    title = ''.join(c for c in tab_title if c.isprintable())
                    
                    # Then remove any HTML special chars
                    title = re.sub(r'[<>&]', '', title)  
                    
                    # Finally limit to a very safe subset of characters
                    title = re.sub(r'[^\w\s.,;:!?()\[\]-]', '', title)  
                    
                    # Truncate long titles
                    title = title[:50] + "..." if len(title) > 50 else title
                    
                    # Additional debugging for each title
                    if DEBUG_MODE:
                        for i, c in enumerate(title):
                            if ord(c) > 127:  # Non-ASCII char
                                logger.debug(f"Non-ASCII char in title: pos={i} char='{c}' ord={ord(c)} hex={hex(ord(c))}")
                    
                    # Similar aggressive sanitization for URLs
                    # First remove all non-printable characters
                    url_clean = ''.join(c for c in tab_url if c.isprintable())
                    
                    # Then remove any HTML special chars
                    url_clean = re.sub(r'[<>&]', '', url_clean)
                    
                    # Keep only URL-safe characters
                    url_simple = re.sub(r'[^\w\s./:?&=\-_~%+]', '', url_clean)
                    
                    # Truncate long URLs
                    url_display = url_simple[:70] + "..." if len(url_simple) > 70 else url_simple
                    
                    if i == selected_index:
                        # Highlight selected tab
                        selected_line = f"<b>[→] <ansiblue>{i+1}.</ansiblue> <ansiyellow>{title}</ansiyellow></b>"
                        url_line = f"    <ansibrightblack>{url_display}</ansibrightblack>"
                        
                        if DEBUG_MODE:
                            # Debug specific lines that might cause issues
                            logger.debug(f"Selected tab {i+1} - title line: {repr(selected_line)}")
                            logger.debug(f"Selected tab {i+1} - url line: {repr(url_line)}")
                            
                        lines.append(selected_line)
                        lines.append(url_line)
                    else:
                        normal_line = f"    <ansiblue>{i+1}.</ansiblue> {title}"
                        url_line = f"    <ansibrightblack>{url_display}</ansibrightblack>"
                        lines.append(normal_line)
                        lines.append(url_line)
                except Exception as tab_error:
                    # Handle any errors with a single tab
                    if DEBUG_MODE:
                        logger.warning(f"Error formatting tab {i}: {tab_error}")
                    # Add safe fallback display
                    if i == selected_index:
                        lines.append(f"<b>[→] <ansiblue>{i+1}.</ansiblue> <ansiyellow>Tab {i+1}</ansiyellow></b>")
                    else:
                        lines.append(f"    <ansiblue>{i+1}.</ansiblue> Tab {i+1}")
            
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
                    logger.error(f"HTML string causing error: {repr(new_html)}")
        
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
            
            # Connect to tab, passing the tab info
            await client.connect(tab.websocket_url, tab=tab)
            
            # Create REPL first so we can use its file change handler
            repl = REPL(client, watcher=None)  # We'll set the watcher later
            
            # Setup file watcher with REPL's file change handler
            watcher = FileWatcher(path, repl.handle_file_change)
            
            # Now set the watcher in the REPL
            repl.watcher = watcher
            
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