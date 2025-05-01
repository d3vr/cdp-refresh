"""Interactive REPL for CDP refresh."""

import asyncio
import logging
import sys
from typing import Dict, Callable, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console

from cdp_refresh.core import CDPClient
from cdp_refresh.watcher import FileWatcher

logger = logging.getLogger(__name__)
console = Console()


class CommandCompleter(Completer):
    """Command completer for the REPL."""
    
    def __init__(self, commands: Dict[str, Dict]):
        """Initialize the completer.
        
        Args:
            commands: Dictionary of available commands
        """
        self.commands = commands
    
    def get_completions(self, document, complete_event):
        """Get completions for the current document.
        
        Args:
            document: Current document
            complete_event: Completion event
            
        Yields:
            Command completions
        """
        word = document.get_word_before_cursor()
        
        if not word:
            # Show all options if no text has been entered
            for cmd in sorted(self.commands.keys()):
                yield Completion(cmd, start_position=0, display_meta=self.commands[cmd]["help"])
            return
            
        # Filter and sort commands
        for cmd in sorted(self.commands.keys()):
            if cmd.startswith(word):
                display_meta = self.commands[cmd]["help"]
                yield Completion(cmd, start_position=-len(word), display_meta=display_meta)


class REPL:
    """Interactive command-line interface with tab completion."""
    
    def __init__(self, client: CDPClient, watcher: FileWatcher):
        """Initialize REPL.
        
        Args:
            client: CDP client
            watcher: File watcher
        """
        self.client = client
        self.watcher = watcher
        self.running = False
        self.refresh_event = asyncio.Event()  # Event to signal file changes
        self.commands: Dict[str, Dict] = {
            "help": {
                "handler": self._cmd_help,
                "help": "Show available commands",
            },
            "reload": {
                "handler": self._cmd_reload,
                "help": "Reload the current page",
            },
            "info": {
                "handler": self._cmd_info,
                "help": "Show current session info",
            },
            "exit": {
                "handler": self._cmd_exit,
                "help": "Exit the program",
            },
            "quit": {
                "handler": self._cmd_exit,
                "help": "Exit the program",
            },
        }
        
        # Setup prompt session with auto-completion
        self.command_history = InMemoryHistory()
        self.completer = CommandCompleter(self.commands)
        self.prompt_style = Style.from_dict({
            'prompt': 'ansibrightyellow',
        })
        self.session = PromptSession(
            completer=self.completer,
            history=self.command_history,
            style=self.prompt_style,
            complete_while_typing=True,
            enable_history_search=True,
        )
    
    async def start(self) -> None:
        """Start the REPL loop."""
        self.running = True
        console.print("[bold cyan]CDP Refresh interactive mode - type [green]help[/] for available commands[/]")
        
        while self.running:
            try:
                command = await self._get_input()
                if command:
                    await self._process_command(command)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                # Handle Ctrl+C more gracefully
                console.print("[yellow]Use 'exit' command to exit[/]")
            except EOFError:
                # Handle Ctrl+D to exit
                await self._cmd_exit()
            except Exception as e:
                logger.error(f"Error processing command: {e}")
    
    async def _get_input(self) -> str:
        """Get user input asynchronously with tab completion.
        
        Returns:
            User input string
        """
        while True:
            try:
                # Create a task for the prompt
                prompt_task = asyncio.create_task(self._prompt_user())
                
                # Wait for either input or a file change event
                refresh_task = asyncio.create_task(self.refresh_event.wait())
                
                done, pending = await asyncio.wait(
                    [prompt_task, refresh_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel any pending tasks
                for task in pending:
                    task.cancel()
                
                # Check which task completed
                if prompt_task in done:
                    # User input was received
                    self.refresh_event.clear()  # Reset the event
                    return await prompt_task
                else:
                    # File change event occurred, clear it and try again
                    self.refresh_event.clear()
                    # Print a blank line after refresh message for better readability
                    console.print("")
                    continue
                    
            except Exception as e:
                logger.error(f"Error getting input: {e}")
                return ""
    
    async def _prompt_user(self) -> str:
        """Get user input using prompt_toolkit.
        
        Returns:
            User input string
        """
        try:
            # Try to use prompt_toolkit for tab completion
            result = await self.session.prompt_async("cdp-refresh> ")
            return result.strip()
        except AttributeError:
            # Fallback to basic input if prompt_toolkit has issues
            logger.warning("Falling back to basic input (no tab completion)")
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: console.input("[bold green]cdp-refresh>[/] ").strip())
    
    async def _process_command(self, command: str) -> None:
        """Process a command.
        
        Args:
            command: Command string
        """
        cmd = command.strip().lower()
        
        if not cmd:
            return
        
        parts = cmd.split()
        cmd_name = parts[0]
        
        if cmd_name in self.commands:
            handler = self.commands[cmd_name]["handler"]
            await handler()
        else:
            console.print(f"[red]Unknown command: {cmd_name}[/]")
            await self._cmd_help()
    
    async def _cmd_help(self) -> None:
        """Show help message."""
        console.print("[bold cyan]Available commands:[/]")
        
        for cmd, info in self.commands.items():
            # Skip aliases like 'quit'
            if cmd in ["quit"]:
                continue
                
            console.print(f"  [bold]{cmd}[/] - {info['help']}")
    
    async def _cmd_reload(self) -> None:
        """Reload the current page."""
        try:
            console.print("[yellow]Reloading page...[/]")
            await self.client.reload_page()
        except Exception as e:
            console.print(f"[red]Error reloading page: {e}[/]")
            
    async def handle_file_change(self) -> None:
        """Handle file change event and set the refresh event.
        
        This method is called by the watcher when files change.
        """
        console.print("[yellow]Files changed, reloading page...[/]")
        try:
            await self.client.reload_page()
            # Signal that a refresh has occurred
            self.refresh_event.set()
        except Exception as e:
            console.print(f"[red]Error reloading page: {e}[/]")
            self.refresh_event.set()  # Still set the event to return to prompt
    
    async def _cmd_info(self) -> None:
        """Show current session info."""
        console.print("[bold cyan]Session info:[/]")
        console.print(f"  Watching directory: [yellow]{self.watcher.path}[/]")
        console.print(f"  Chrome connection: [yellow]{self.client.base_url}[/]")
    
    async def _cmd_exit(self) -> None:
        """Exit the program."""
        import asyncio  # Import locally to ensure it's available
        
        self.running = False
        console.print("[yellow]Exiting...[/]")
        
        try:
            # Clean up resources
            if hasattr(self, 'client') and self.client:
                await self.client.disconnect()
                
            # Simplify task cancellation to avoid potential issues
            # Force exit immediately - the parent CLI handler will clean up tasks
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error during exit: {e}")
            # Force exit even if there's an error
            sys.exit(1)