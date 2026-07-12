# Contributing to Zer0Fit

Thank you for your interest in contributing to Zer0Fit! We welcome contributions of all kinds — bug reports, feature requests, documentation improvements, and code changes.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Issue Reporting](#issue-reporting)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone. Be kind, constructive, and professional.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/Zer0Fit.git`
3. Add the upstream remote: `git remote add upstream https://github.com/porespellar/Zer0Fit.git`
4. Create a branch: `git checkout -b my-feature-branch`

## Development Setup

### Prerequisites

- Docker with NVIDIA Container Toolkit (GPU required)
- At least 16GB VRAM on the GPU

### Local Development

```bash
# Build and start the server
docker compose --profile gpu up --build -d

# Check health
curl http://localhost:8002/health

# Check the MCP endpoint
curl http://localhost:8002/mcp
```

## Pull Request Process

1. **Create an issue** first for significant changes — discuss the approach before investing time
2. **Keep PRs focused** — one feature/fix per PR. Large changes should be broken into smaller PRs
3. **Update documentation** — README.md, AGENTS.md, or any other relevant files
4. **Test your changes** — verify the server starts, health endpoint responds, and model inference works
5. **Update the PR template** — fill out all relevant sections
6. **Squash merge** will be used — ensure your commit messages are clean

## Coding Standards

This project follows the conventions in [AGENTS.md](AGENTS.md):

- Python 3.13+, async/await throughout
- Type hints on all public functions
- Logging via `logging.getLogger("zer0fit.<module>")`
- Lazy imports for heavy deps (timesfm, tabfm, torch) inside loader functions
- No hardcoded secrets — all config via environment variables

## Testing

Before submitting a PR, please verify:

1. The server starts without errors: `docker compose --profile gpu up --build -d`
2. Health endpoint responds: `curl http://localhost:8002/health`
3. MCP endpoint is reachable: `curl http://localhost:8002/mcp`
4. Any new tools or parameters are documented

## Issue Reporting

- **Bug reports**: Include server logs, environment details, and steps to reproduce
- **Feature requests**: Explain the use case and desired behavior clearly
- **Questions**: Use GitHub Discussions (Q&A category) rather than issues

## Legal

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE) that covers this project. See the [DISCLAIMER.md](DISCLAIMER.md) for the project's liability disclaimer.
