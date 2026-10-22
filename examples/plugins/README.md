# Example plugins

Start with **Event logger** to see how a plugin works. Each folder contains readable Python,
its `videoforge-plugin.toml` manifest, and a README covering setup and expected behavior.

| Example | Demonstrates | Requires |
| --- | --- | --- |
| [Event logger](event_logger/README.md) | All four event slots, job/app logging, and a text setting | VideoForge only |
| [Library scan](library_scan/README.md) | Success filtering, a choice setting, credentials, and an HTTP request | A Jellyfin server and API key |

## Install an example

1. Download its `VideoForge-plugin-<id>-<version>.zip` from the matching
   [VideoForge release](https://github.com/jessielw/VideoForge/releases).
2. Open **Settings → Plugins → Install ZIP…**, select the ZIP, review it, and choose **Install on restart**.
3. Expand **Details and settings → Configure** and fill in the example's settings.
4. Restart VideoForge. The plugin should show **Running**.

You can also copy an example's entire folder into the plugin folder shown in Settings, then restart.
Keep the manifest and Python module together. Installing an example does not require extra Python packages.

## Build the ZIPs from source

From the repository root, using Python 3.12 or newer:

```sh
python scripts/build_plugin_examples.py
```

The ZIPs appear in `build/plugin-examples/`. They contain the README, manifest and Python code from
these folders. Generated ZIPs are release assets; the source folders remain the editable examples.

The release workflow runs this command and attaches the ZIPs to the draft release alongside the
Windows portable application. A manual workflow run without a release tag provides them as an
Actions artifact instead.

For your own plugin, copy Event logger's folder, choose a unique `id` and `module`, and adapt its
callbacks. See the [plugin guide](https://jessielw.github.io/VideoForge/plugins/) for the API,
settings declarations, dependency packaging and execution behavior.
