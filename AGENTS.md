# AGENTS

## Purpose

- Provide clear, repo-specific instructions for autonomous agents working in this repository.

## General Guidelines

- Be concise and explain coding steps briefly when making code changes; include code snippets where relevant.
- For non-trivial edits, provide a short plan. For small, low-risk edits, implement and include a one-line summary.
- Focus on a single conceptual change at a time when public APIs or multiple modules are affected.
- Maintain project style and Python 3.12+ compatibility. Target latest Home Assistant core.
- If deviating from these guidelines, explicitly state which guideline is deviated from and why.

## Project Context

- This project replaces an OpenMQTTGateway device with an ESPHome build using `rtl_433_ESP`.
- The main firmware configuration is `garage-rtl433.yaml`.
- The local custom component is in `components/rtl433_native/`.
- Tests live in `tests/`.

## Agent permissions and venv policy

- Agents may create and use a repository-local venv at `./.venv` and should reference `./.venv/bin/python` when running commands.
- Installing packages from repo manifests (e.g., `requirements-dev.txt`, `pyproject.toml`) into `./.venv` is allowed for running tests or local tooling; avoid unrelated network operations without explicit consent.

## Coding standards

- Add typing annotations to all functions and classes (including return types).
- Add or update docstrings for all files, classes and methods, including private methods and nested methods. Method docstrings must follow the Google Style.
- Do not use `cast` or `assert` in the main code. They are ok in tests.
- Preserve existing comments and keep imports at the top of files.
- Follow existing repository style; run `./scripts/lint`.

## Local tooling note

- Use the repo's `prek`, and `pytest` commands inside `./.venv`. You must always run these inside `./.venv`.
- By default, run the full pytest suite. If running targeted tests, explain why.

## Error handling & logging

- Catch specific exceptions (do not catch Exception directly).
- Add robust error handling and clear debug/info logs.
- If tests fail due to missing dev dependencies, either install them into `./.venv` (if allowed) or report exact `pip install` commands.

## Testing

- Use `pytest`.
- Add typed, well-documented tests in `tests/` and use fixtures in `conftest.py`.
- One test module per integration source file; achieve high coverage (target >= 80%).
- Parameterize tests when appropriate; avoid duplicate test functions.

## PR & branch behavior

- Create branches or PRs only when explicitly requested. Do not open PRs autonomously.

## Network / install consent

- Obtain explicit consent before any network operations outside the repository not strictly needed to run local tests.
- Package installs required for running tests are allowed when user approves.

## CI/CD

- Use GitHub Actions for CI/CD where applicable.

## Conventions for changes and documentation

- When editing code, prefer fixing root causes over surface patches.
- Keep changes minimal and consistent with the codebase style.
- Add tests for any changed behavior and update documentation if needed.
