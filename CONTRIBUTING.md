# Contributing

Thanks for contributing to `aw-index-cli`!

## Development setup

Install the package in editable mode with the dev extras (pytest):

```bash
python3 -m pip install -e ".[dev]"
```

## Running the tests

```bash
pytest
```

## Pre-commit

Formatting and linting run via [pre-commit](https://pre-commit.com/). Install the
hooks once; they then run on every commit:

```bash
pre-commit install
pre-commit run --all-files   # or run against the whole repo on demand
```

## Commit and PR conventions

- Write commit messages and PR titles as [Conventional Commits](https://www.conventionalcommits.org/)
  (e.g. `feat(compose): …`, `fix(cli): …`, `docs: …`).
- Sign off every commit for the [DCO](https://developercertificate.org/) — add a
  `Signed-off-by` trailer with `git commit -s`.
