# Contributing to MCP Atlassian

Thank you for your interest in contributing to MCP Atlassian! This document provides guidelines and instructions for contributing to this project.

## Development Setup

1. Make sure you have Python 3.10+ installed
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. Fork the repository
4. Clone your fork: `git clone https://github.com/YOUR-USERNAME/mcp-atlassian.git`
5. Add the upstream remote: `git remote add upstream https://github.com/sooperset/mcp-atlassian.git`
6. Install dependencies:
```bash
uv sync --frozen --all-extras --dev
```
7. Set up pre-commit hooks:
```bash
pre-commit install
```
8. Set up environment variables (copy from .env.example):
```bash
cp .env.example .env
```

## Development Setup with local VSCode devcontainer

1. Clone your fork: `git clone https://github.com/YOUR-USERNAME/mcp-atlassian.git`
2. Add the upstream remote: `git remote add upstream https://github.com/sooperset/mcp-atlassian.git`
3. Open the project with VSCode and open with devcontainer
4. Add this bit of config to your `.vscode/settings.json`:
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
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

2. Make your changes

3. Ensure tests pass:
```bash
uv run pytest

# With coverage
uv run pytest --cov=mcp_atlassian
```

4. Run code quality checks using pre-commit:
```bash
pre-commit run --all-files
```

6. Commit your changes with clear, concise commit messages referencing issues when applicable

7. Submit a pull request to the main branch

## Code Style

- We use pre-commit hooks to enforce code quality
- Code quality tools include:
  - `ruff-format` for code formatting
  - `ruff` for linting, with configured rules and fixes
  - `mypy` for type checking, with specific error code configurations
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

Releases follow semantic versioning:
- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

---

Thank you for contributing to MCP Atlassian!
