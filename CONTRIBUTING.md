# Contributing to LocoDex Deep Search

We love your input! We want to make contributing to LocoDex Deep Search as easy and transparent as possible.

## Development Process

We use GitHub to sync code, track issues, feature requests, and accept pull requests.

## Pull Requests

1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. If you've changed APIs, update the documentation.
4. Ensure the test suite passes.
5. Make sure your code lints.
6. Issue that pull request!

## Any contributions you make will be under the MIT Software License

When you submit code changes, your submissions are understood to be under the same [MIT License](LICENSE) that covers the project.

## Report bugs using GitHub's [issue tracker](https://github.com/berketez/LocoDex-deep-search/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/berketez/LocoDex-deep-search/issues/new).

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

## Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/LocoDex-deep-search.git
cd LocoDex-deep-search

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Install dependencies
cd deep_research_service
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Start development server
python server.py
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable names
- Add docstrings for functions and classes
- Keep functions small and focused

## License

By contributing, you agree that your contributions will be licensed under its MIT License.

## Contact

Berke Tezgöçen - berketezgocen@hotmail.com