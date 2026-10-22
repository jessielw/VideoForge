# Library scan (Jellyfin)

Ask Jellyfin to refresh its libraries after successful encoding. This example demonstrates
settings, a stored API key, filtering job results and making an HTTP request. It uses `niquests`,
which VideoForge already includes; no additional Python packages are needed.

The request refreshes all Jellyfin libraries through `POST /Library/Refresh`.

## Install and configure

1. In Jellyfin, open **Dashboard → API Keys** and create a key for VideoForge.
2. Download `VideoForge-plugin-library_scan-1.0.zip` from a
   [VideoForge release](https://github.com/jessielw/VideoForge/releases), or run
   `python scripts/build_plugin_examples.py` from the repository root.
3. Import the ZIP through **Settings → Plugins → Install ZIP…**.
4. Open **Details and settings → Configure Library scan**, enter the server URL and API key, and select when to scan.
5. Restart VideoForge and confirm the plugin shows **Running** with **Enabled** checked.

Alternatively, copy this folder into the plugin folder shown in Settings, configure it, and restart.
The URL must be reachable from the machine running VideoForge. In Docker, `localhost` refers to
the VideoForge container; use Jellyfin's reachable container name or host address instead.

## Settings

| Key | Form label | Required/default | Effect |
| --- | --- | --- | --- |
| `url` | Jellyfin server URL | Required | Jellyfin's base URL, such as `http://localhost:8096` |
| `api_key` | Jellyfin API key | Required | Sent in the request's `X-Emby-Token` header |
| `when` | Scan after | `queue` | `job`: after each successful job; `queue`: once after a queue containing a successful job |

You can also configure the plugin in `videoforge.local.toml`:

```toml
[plugins.library_scan]
url = "http://localhost:8096"
api_key = "YOUR_JELLYFIN_API_KEY"
when = "queue"
```

Saved form values override TOML values and take effect after restart. Leave a stored password
unchanged to keep it. Use **Reset overrides** to return to TOML values or defaults.

## Expected behavior

With **Scan after** set to `queue`, finish at least one successful job and let the queue stop.
The application log in the data folder's `logs/` directory should contain `Jellyfin: scanning`.
With `job` selected, each successful job's Log tab should contain `Jellyfin: scanning`.

Failed, invalid, skipped and cancelled jobs do not trigger a per-job scan. A queue without a
successful job does not trigger a scan. A failed HTTP request is reported in the relevant log;
it does not fail the encode. Requests have a 30-second timeout and are not retried by this example.

## Read the source

- [library_scan.py](library_scan.py) contains result filtering and the Jellyfin request.
- [videoforge-plugin.toml](videoforge-plugin.toml) declares the URL, password and choice fields.

Configure your API key locally. Passwords are masked in the form, but configuration backups include
them; keep the distributed source and example ZIP free of your credentials.
