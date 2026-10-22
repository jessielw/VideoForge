# Command line

From a source checkout, prefix commands with `uv run`. In a Windows portable build, use
`.\videoforge.cmd` in place of `uv run videoforge`.

```sh
uv run videoforge --help
uv run videoforge serve --help
```

## Serve

```sh
uv run videoforge serve --no-browser --port 8765
```

| Option | Meaning |
| --- | --- |
| `--host` | Listening interface; default `127.0.0.1` |
| `--port` | Listening port; default `8765` |
| `--allow-host` | Additional exact UI hostname or IP, without port; repeatable |
| `--allow-origin` | Additional browser origin such as `https://video.example`; repeatable |
| `--no-browser` | Do not open a browser automatically |
| `--window` | Open the desktop window; requires the `desktop` extra |
| `--data-dir` | Override the queue and application data folder |
| `--plugin-management` / `--no-plugin-management` | Allow or disable plugin ZIP installation, removal and configuration; defaults to enabled for loopback bindings only |

The server has no login. Changing the host to `0.0.0.0` makes it listen beyond loopback; provide
your own access control if remote users can reach it.

Requests must use `localhost`, `127.0.0.1`, `::1`, the concrete listening address, or an explicit
`--allow-host`. Wildcard listening addresses do not allow arbitrary Host headers. Browser mutations
and WebSockets must be same-origin, or use an explicit `--allow-origin`. Originless CLI/desktop
requests remain supported. These checks do not add authentication.

Vite's default proxy preserves Host, so `http://localhost:5173` works without extra flags. For an
authenticated reverse proxy, allow its public hostname and, if it rewrites Host or terminates TLS,
its browser origin:

```sh
uv run videoforge serve --no-browser --allow-host video.example --allow-origin https://video.example
```

Forward WebSocket upgrades too. Configure the public address explicitly; forwarded Host headers
alone never expand the allowlist.

## Plan

Pair sources with existing encodes, subtitles, and chapters, then inspect the profile's track plan:

```sh
uv run videoforge plan "D:\Sources\Season 01" --profile manual --orig-lang en --out plan.json
```

`--only` limits sources by substrings in their filenames. `--out` writes serialized plans for
`run`. A blocking plan returns exit code **1**; an unblocked set returns **0**.

The CLI plans from discovered inputs and profile rules. It does not export the queue editor's
templates or per-job UI settings. Use the web queue for the full interactive video workflow.

## Run

```sh
uv run videoforge run plan.json --out-dir "D:\Finished" --verbose
```

`--out-dir` is required. `--only` filters by source-name substrings, and `-v` / `--verbose` shows tool
output. Each plan runs through its pipeline and output validation.

The command returns **0** when every run is done, **1** for other job results, and **130** when
interrupted with Ctrl+C. Configuration comes from the TOML files rather than saved server UI overrides.

## Validate

Run the chosen profile's release checks on media files or MediaInfo `.txt` reports:

```sh
uv run videoforge validate "D:\Finished\Episode.mkv" --profile manual
uv run videoforge validate report.txt --profile manual --summary --min-severity block
```

`--summary` prints issue counts instead of per-file details. `--min-severity` accepts `warn` or
`block`. A blocking result returns **1**.

Standalone validation uses `Profile.validate_release`. The manual profile's detailed
**plan-versus-output** checks happen during job execution; standalone `validate --profile manual`
does not reconstruct those checks without the original plan. A custom profile can supply
release-wide rules.
