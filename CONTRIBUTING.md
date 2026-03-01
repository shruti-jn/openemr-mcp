# Contributing to openemr-mcp

Thanks for your interest in contributing.

## Getting Started

1. Fork the repository and create a feature branch.
1. Create a virtual environment and install dependencies.
1. Run tests before submitting a pull request.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Development Guidelines

- Keep changes focused and scoped to a single concern.
- Add or update tests for behavior changes.
- Preserve backwards compatibility for public tool names and payload shapes when possible.
- Use clear commit messages and pull request descriptions.

## Pull Request Checklist

- Tests pass locally.
- New behavior is documented in `README.md` when applicable.
- Any configuration or environment variable changes are reflected in `.env.example`.

## Reporting Bugs

Open an issue with:

- Expected behavior
- Actual behavior
- Steps to reproduce
- Environment details (OS, Python version, package version)

## Questions

For support or feature discussions, open a GitHub issue in this repository.
