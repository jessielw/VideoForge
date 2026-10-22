# Contributing

Start with a [source checkout](../getting-started/source.md). The backend is Python / FastAPI; the
frontend is Svelte 5, Vite, and TypeScript. Read the [architecture](architecture.md) before changing
planning, execution, or saved job data.

## Development servers

Start the backend in one terminal:

```sh
uv run videoforge serve --no-browser
```

Start Vite in another:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies API requests to the backend.

## Python checks

```sh
uv sync --extra desktop
uv run pytest -q
uv run poe typecheck
uv run poe lint
uv run poe format-check
```

Tests requiring external tools or VapourSynth plugins skip when those tools are unavailable.
Use the relevant real-media tests for changes to timing, color, subtitles, muxing, and reuse;
unit checks alone do not establish media correctness.

`poe format` applies Ruff fixes and formatting. Run it on your intended changes before review.

## Frontend checks

From `frontend/`:

```sh
npm run check
npm run build
```

The app on port **8765**, including the desktop window, serves `frontend/dist`. After editing
the frontend, run `npm run build` and reload that app to see the changes. Port **5173** serves
the source directly through Vite during development.

Run browser tests with `npm run test:browser`. To check the built app, build first and set
`PLAYWRIGHT_PREVIEW=1` before running the browser tests (PowerShell: `$env:PLAYWRIGHT_PREVIEW = '1'`).

## Extension points

Use a [profile](profiles.md) for track planning and release checks. Use an [action](../actions.md)
or [plugin](../plugins.md) for work triggered by job and queue events. Keep HTTP-specific behavior
in `server/` and the shared execution engine under `core/`.

## Documentation

Update the relevant guide when changing behavior, options, or output formats. Preview and publishing
commands are in [Documentation and releases](documentation.md).
