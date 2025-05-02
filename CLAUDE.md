# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test Commands
- Install development environment: `uv venv && source .venv/bin/activate && uv pip install -e .`
- Run application: `python main.py`
- Run specific test: `pytest tests/test_file.py::test_function -v`
- Run all tests: `pytest`
- Check types: `mypy src/`
- Lint code: `ruff check src/`
- Format code: `ruff format src/`

## Code Style Guidelines
- **Imports**: Group imports: stdlib, third-party, local. Sort alphabetically within groups.
- **Typing**: Use type hints for all function parameters and return values.
- **Naming**: Follow PEP8 - snake_case for variables/functions, CamelCase for classes.
- **Formatting**: Line length <= 88 characters. Use f-strings for string formatting.
- **Error Handling**: Use specific exceptions. Handle browser connection errors gracefully.
- **Comments**: Include docstrings for modules, classes, and functions.
- **Browser Interaction**: Abstract CDP operations to make browser interaction more maintainable.
- **File Watching**: Implement robust error handling for file system operations.
- No need to check types from now on