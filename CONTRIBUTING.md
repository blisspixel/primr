# Contributing to Primr

Thanks for your interest in contributing to Primr! This document provides guidelines for contributing.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/primr.git`
3. Set up the development environment:
   ```bash
   cd primr
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # or: source .venv/bin/activate  # macOS/Linux
   pip install -e ".[dev]"
   playwright install chromium
   ```
4. Copy `.env.example` to `.env` and add your API keys

## Development Workflow

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_cli.py -v

# Run with coverage
python -m pytest tests/ --cov=src/primr --cov-report=html
```

### Code Quality

Before submitting a PR, ensure your code passes all checks:

```bash
# Type checking
python -m mypy src/primr/ --ignore-missing-imports

# Linting
python -m ruff check src/primr/

# Security scan
python -m bandit -r src/primr/ -c .bandit
```

### Code Style

- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and under 50 lines when possible

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes with clear, atomic commits
3. Ensure all tests pass and code quality checks succeed
4. Update documentation if needed
5. Submit a PR with a clear description of changes

### PR Guidelines

- Keep PRs focused on a single feature or fix
- Include tests for new functionality
- Update CHANGELOG.md for user-facing changes
- Reference any related issues

## Reporting Issues

When reporting bugs, please include:

- Python version (`python --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant error messages or logs

## Feature Requests

Feature requests are welcome! Please:

- Check existing issues first to avoid duplicates
- Describe the use case and expected behavior
- Explain why this would be useful

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

Feel free to open an issue for questions or discussions about the project.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
