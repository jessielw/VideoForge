# Contributing

## Branches

- Branch from `dev`, not `main`.
- Open pull requests against `dev`.
- `main` holds tagged releases. Changes reach it from `dev` when a release is cut.

```sh
git fetch origin
git switch -c my-change origin/dev
```

## Before opening a pull request

```sh
uv run pytest -q
uv run poe typecheck
uv run poe lint
uv run poe format-check
cd frontend && npm run check
```

Setup, development servers, and the full set of checks are in the [contributing guide](https://jessielw.github.io/VideoForge/development/contributing/). Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing planning, execution, or saved job data.
