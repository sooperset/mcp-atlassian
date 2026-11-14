# Contributing to MCP Atlassian

Thank you for your interest in contributing to MCP Atlassian! This document provides guidelines and instructions for contributing to this project.

## Development Setup

1. Make sure you have Python 3.10+ installed
1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
1. Fork the repository
1. Clone your fork: `git clone https://github.com/YOUR-USERNAME/mcp-atlassian.git`
1. Add the upstream remote: `git remote add upstream https://github.com/sooperset/mcp-atlassian.git`
1. Install dependencies:

    ```sh
    uv sync
    uv sync --frozen --all-extras --dev
    ```

1. Activate the virtual environment:

    __macOS and Linux__:

    ```sh
    source .venv/bin/activate
    ```

    __Windows__:

    ```powershell
    .venv\Scripts\activate.ps1
    ```

1. Set up pre-commit hooks:

    ```sh
    pre-commit install
    ```

1. Set up environment variables (copy from .env.example):

    ```bash
    cp .env.example .env
    ```

## Development Setup with local VSCode devcontainer

1. Clone your fork: `git clone https://github.com/YOUR-USERNAME/mcp-atlassian.git`
1. Add the upstream remote: `git remote add upstream https://github.com/sooperset/mcp-atlassian.git`
1. Open the project with VSCode and open with devcontainer
1. Add this bit of config to your `.vscode/settings.json`:

    ```json
    {
        "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
        "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true
        }
    }
    ```

## Development Workflow

1. Create a feature or fix branch:

    ```sh
    git checkout -b feature/your-feature-name
    # or
    git checkout -b fix/issue-description
    ```

1. Make your changes

1. After changing tool signatures or registrations, run `uv run python scripts/generate_tool_docs.py` and commit the diff; CI (`Docs / check`) enforces this

1. Ensure tests pass:

    ```sh
    uv run pytest

    # With coverage
    uv run pytest --cov=mcp_atlassian
    ```

1. Run code quality checks using pre-commit:

    ```bash
    pre-commit run --all-files
    ```

1. Commit your changes with clear, concise commit messages referencing issues when applicable

1. Submit a pull request to the main branch

## Code Style

- Run `pre-commit run --all-files` before committing
- Code quality tools (managed by pre-commit):
  - `ruff` for formatting and linting (88 char line limit)
  - `pyright` for type checking (preferred over mypy)
  - `prettier` for YAML/JSON formatting
  - Additional checks for trailing whitespace, file endings, YAML/TOML validity
- Follow type annotation patterns:
  - `type[T]` for class types
  - Union types with pipe syntax: `str | None`
  - Standard collection types with subscripts: `list[str]`, `dict[str, Any]`
- Add docstrings to all public modules, functions, classes, and methods using Google-style format:

        ```python
        def function_name(param1: str, param2: int) -> bool:
            """Summary of function purpose.

            More detailed description if needed.

            Args:
                param1: Description of param1
                param2: Description of param2

            Returns:
                Description of return value

            Raises:
                ValueError: When and why this exception is raised
            """
        ```

## Pull Request Process

1. Fill out the PR template with a description of your changes
2. Ensure all CI checks pass
3. Request review from maintainers
4. Address review feedback if requested

## Release Process

Versions use `0.MINOR.PATCH`, the same scheme as [uv](https://docs.astral.sh/uv/reference/policies/versioning/) and [Ruff](https://docs.astral.sh/ruff/versioning/):

- **PATCH** (`0.24.3` → `0.24.4`): new features and bug fixes. We aim to release about once a week.
- **MINOR** (`0.24.x` → `0.25.0`): any change that can break an existing setup, such as removing or renaming a tool, parameter, or response field, changing a default or the meaning of an environment variable, or dropping a Python version. The release notes open with a **Breaking changes** section.
- Security fixes ship as a PATCH release as soon as they are ready.

Pinning to a minor line (`mcp-atlassian>=0.24,<0.25` or the Docker tag `:0.24`) keeps you on features, fixes, and security patches without breaking changes.

---

Thank you for contributing to MCP Atlassian!
