# Contributing

Thanks for helping improve Moodtag. This guide covers development and release
checks; user setup and CLI usage are in the [README](README.md) and
[`docs/`](docs/).

## Development

Requirements: Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --dev
uv run moodtag --help
```

Keep API credentials in environment variables or a local, ignored `.env` file.
Never commit credentials.

Run the unit suite before submitting changes:

```sh
uv run python -m unittest discover -s tests
```

Tests use a fake Eagle client and mocked model responses; they do not contact a
real Eagle library or model service. To run the configured local checks:

```sh
uv run pre-commit run --all-files
```

The pre-commit hooks format and lint Python code and compile the project
sources. The pre-push hook also runs the release check.

## Eagle integration checks

The real Eagle E2E suite imports temporary images and moves its test items to
the Eagle trash during cleanup. Run it only with a disposable test folder or
after reviewing the script's cleanup behavior:

```sh
uv run python scripts/e2e_moodtag.py --board '<test-folder-id-or-name>'
```

Live-model checks in `scripts/e2e_live_batch.py` and
`scripts/e2e_protocol_matrix.py` call configured model services. The protocol
matrix also clears tags and annotations in its confirmed Eagle folder. Review
the script and target folder before running either check; never commit API
keys or generated reports.

## Build and release

Run the release gate on a clean working tree before publishing:

```sh
scripts/release_check.sh
```

It runs unit tests, builds and validates the wheel and source distribution,
then smoke-tests the installed CLI. On Apple Silicon macOS it also builds and
smoke-tests the `.pkg` installer and `.dmg`. Build outputs in `dist/`,
`build/`, and `*.egg-info/` are generated and should not be committed.

Releases are published by the GitHub Actions `Publish` workflow. Before
creating a release tag:

1. Update `version` in `pyproject.toml`.
2. Run `scripts/release_check.sh` and commit the release changes.
3. Push a matching version tag, such as `v0.1.6`.

The workflow publishes the Python distributions to PyPI using Trusted
Publishing and attaches Apple Silicon macOS installer artifacts to the GitHub
Release. The PyPI project must trust this repository's `Publish` workflow and
use the `pypi` environment.
