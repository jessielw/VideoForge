# Docker

The Linux **amd64** image is `ghcr.io/jessielw/videoforge`. It contains the application and the free
media tools: MKVToolNix, x264, x265, SVT-AV1, FFmpeg, MP4Box, opus-tools, DeeZy, truehdd, HDR metadata
tools, Wine, and the bundled VapourSynth plugins.

## Platform support

The published image targets `linux/amd64`. ARM64 images and macOS Docker validation are deferred;
running this image through emulation on Apple Silicon does not establish compatibility or performance
for all tools, Wine encoders or CPU-specific plugins.
For a self-managed native installation with your own tools and compiled plugins, see
[macOS and ARM64 from source](source.md#macos-and-arm64).

## Start with Compose

1. Save [compose.yaml](https://github.com/jessielw/VideoForge/blob/main/compose.yaml) in a new folder.
2. Replace `/path/to/media` with your media folder. Set `user` to the UID and GID that can write to it.
3. Create the host folders `data` and `tools`, with write access for that UID and GID.
4. Start the service:

    ```sh
    docker compose up -d
    ```

5. Open [http://127.0.0.1:8765](http://127.0.0.1:8765) and check **Settings**.

```yaml
services:
  videoforge:
    image: ghcr.io/jessielw/videoforge:latest
    container_name: videoforge
    user: "1000:1000"
    ports:
      - "127.0.0.1:8765:8765"
    volumes:
      - ./data:/data
      - ./tools:/tools
      - /path/to/media:/media
    restart: unless-stopped
```

Enter paths as the **container** sees them: `/media/Movies/Film.mkv`, for example.
Each source's work folder is created beside that source, so the media mount must be writable.

## Mounted folders

| Container path | Purpose |
| --- | --- |
| `/data` | Queue database, templates, settings, logs, archived job records, and plugins |
| `/media` | Your sources, work folders, and outputs; add other writable mounts if needed |
| `/tools` | DEE, qaac, and additional VapourSynth plugins you supply |

## Add DEE or qaac

These files are not included in the image. Restart the container after adding them.

| Tool | Location inside the container |
| --- | --- |
| DEE, Linux | `/tools/dee/dee`, with its license beside it |
| DEE, Windows through Wine | `/tools/wine/dee/dee.exe`, with its license beside it |
| qaac through Wine | `/tools/wine/qaac/qaac64.exe`, with the `QTfiles64` folder beside it |
| Extra VapourSynth plugins | `/tools/vs-plugins/*.so` |

Linux DEE files need executable permission. If a copy over SMB or Unraid's New Permissions removed
it, run `chmod +x tools/dee/*` in the host folder containing your Compose file.

## Network access

VideoForge has **no login**. The Compose example binds the published port to the Docker host's
loopback interface. If you need remote access, put it behind your own proxy with authentication.
Publishing `8765:8765` exposes it on the host's network interfaces and lets other people who can
reach that port run jobs and modify settings.

On Unraid, add a port mapping for container port **8765**. Without a published port, the application
cannot be reached outside the container. Restrict access to that published port or use an authenticated proxy.

To open the page at a LAN address or proxy hostname, set `VIDEOFORGE_ALLOW_HOST` to that hostname or
IP, without the port. Otherwise the page answers *Host is not allowed*. If the proxy changes Host or
terminates TLS, also set `VIDEOFORGE_ALLOW_ORIGIN=https://<public-hostname>` (include a nonstandard
port when used). Binding to `0.0.0.0` alone does not permit arbitrary browser hosts.

Command actions are disabled in the Docker configuration. Their opt-in setting is documented under
[Actions](../actions.md#commands).

## Environment variables

| Variable | Meaning |
| --- | --- |
| `VIDEOFORGE_ALLOW_HOST` | Hostnames or IPs you open the page at, without port; comma-separated, such as `192.168.1.50,tower` |
| `VIDEOFORGE_ALLOW_ORIGIN` | Browser origins for a proxy that rewrites Host, such as `https://video.example`; comma-separated |
| `VIDEOFORGE_PLUGIN_MANAGEMENT` | `true` allows installing, removing and configuring plugins from the page; off by default in Docker |
| `PUID` / `PGID` | Run as this user and group, set together (Unraid: `99` / `100`); the container must start as root |
| `UMASK` | File-creation mask for what it writes: 1-4 octal digits, such as `002` for group-writable files |
| `TZ` | Time zone for logs and job records, such as `America/New_York`; default UTC |
| `VIDEOFORGE_PORT` | Listening port inside the container; default `8765`. Change the host side of the port mapping instead. |

The image already sets `VIDEOFORGE_HOST=0.0.0.0` and `VIDEOFORGE_DATA_DIR=/data`. Each `serve`
option has a matching variable; a command-line option wins over its variable, and `--allow-host` /
`--allow-origin` add to the variable's list. See [Serve options](../reference/cli.md#serve).

`PUID` / `PGID` are an alternative to `user:` (`docker run --user`). With them, the container hands
`/data` to that user on start, so a queue made while it ran as root stays usable. Media mounts and
`/tools` keep their ownership. An invalid `PUID`, `PGID`, `UMASK` or `TZ` stops the container with a
message in its log.

### Unraid

In the container's template, add a **Variable** for each setting:

1. `VIDEOFORGE_ALLOW_HOST`: the server's IP and name, such as `192.168.1.50,tower`
2. `PUID`: `99` and `PGID`: `100` (`nobody:users`), so files on your shares are not owned by root
3. Optional: `UMASK`: `000` to match Unraid's default share permissions

Unraid already passes `TZ`.

Leave **Post Arguments** empty. Text there replaces the image's command.

## Update and inspect logs

```sh
docker compose pull
docker compose up -d
docker compose logs -f videoforge
```

Back up `/data` with the service stopped before updating. Keep the media mounts at the same
container paths so saved jobs still find their inputs.

## Build locally

```sh
docker build -t videoforge .
```

The default build uses the published plugins image. To build the plugins too:

```sh
docker build -t videoforge-plugins vsplugins
docker build --build-arg PLUGINS_IMAGE=videoforge-plugins -t videoforge .
```

Building FFmpeg, MP4Box, x264, and the plugins can take **30 minutes or more**.

Next: [create your first job](first-job.md).
