# CDP Refresh

A developer tool that watches for file changes in your project directory and automatically refreshes the selected Chrome tab using Chrome DevTools Protocol (CDP).

## Features

- Watch files for changes and automatically refresh browser
- Interactive command-line interface with tab completion
- Select which Chrome tab to refresh
- Support for standard gitignore patterns
- Custom file ignore patterns
- Cross-platform support (Windows, macOS, Linux)

## Prerequisites

1. **Python:** Version 3.11 or higher
2. **Chrome/Chromium with Remote Debugging:** Launch your browser with remote debugging enabled:
   ```bash
   # Linux
   google-chrome --remote-debugging-port=9222
   
   # macOS
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
   
   # Windows
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```

## Installation

```bash
# Install with pip
pip install cdp-refresh

# Or install in development mode
git clone <repo-url>
cd cdp-refresh
uv venv && source .venv/bin/activate
uv pip install -e .
```

## Usage

Run CDP Refresh and select a tab to refresh:

```bash
cdp-refresh /path/to/watch
```

### Command-line Options

```
Arguments:
  PATH                      Directory to watch for changes [default: .]

Options:
  -h, --host TEXT           Chrome host [default: localhost]
  -p, --port INTEGER        Chrome debugging port [default: 9222]
  -i, --ignore TEXT         Ignore pattern (can be used multiple times)
  --no-git-ignore           Disable using .gitignore patterns
  -v, --verbose             Enable verbose logging
  -d, --debug               Enable debug mode with detailed error information
  --help                    Show this message and exit
```

### Interactive Commands

Once running, you can use these commands:
- `help` - Show available commands
- `reload` - Manually reload the current page
- `select-tab` - Select a different tab to refresh
- `info` - Show current session info
- `exit` or `quit` - Exit the program

## Architecture

CDP Refresh is built with an asynchronous architecture using Python's asyncio:

- **CLI Module**: Entry point and argument handling
- **Core Module**: Chrome DevTools Protocol client for browser interaction
- **REPL Module**: Interactive command interface with tab completion
- **Watcher Module**: File system monitoring and change detection
- **Browser Module**: Cross-platform Chrome detection utilities

## Libraries

| Library | Purpose |
|---------|---------|
| Typer | Command-line interface argument parsing |
| Rich | Terminal formatting and output styling |
| prompt_toolkit | Interactive REPL with tab completion |
| watchfiles | Fast file system monitoring |
| websockets | WebSocket communication with Chrome DevTools Protocol |
| httpx | HTTP client for Chrome DevTools Protocol API |
| pydantic | Data validation for Chrome tab information |

## Contributing

Contributions are welcome! Here's how to contribute:

1. Set up development environment:
   ```bash
   git clone <repo-url>
   cd cdp-refresh
   uv venv && source .venv/bin/activate
   uv pip install -e .
   ```

2. Ensure your changes pass all checks:
   ```bash
   # Type checking
   mypy src/
   
   # Linting
   ruff check src/
   
   # Formatting
   ruff format src/
   ```

3. Follow code style guidelines:
   - Use type hints for all function parameters and return values
   - Follow PEP8 naming conventions
   - Line length ≤ 88 characters
   - Use f-strings for string formatting
   - Include docstrings for modules, classes, and functions
   - Use specific exceptions and handle browser connection errors gracefully

4. Submit a pull request with your changes

## License

[MIT License](LICENSE)