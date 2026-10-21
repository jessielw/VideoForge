# Docker

The Linux **amd64** image is `ghcr.io/jessielw/videoforge`. It contains the application and the free
media tools: MKVToolNix, x264, x265, SVT-AV1, FFmpeg, MP4Box, opus-tools, DeeZy, truehdd, HDR metadata
tools, Wine, and the bundled VapourSynth plugins.

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

For a LAN address or proxy hostname, add `--allow-host <hostname-or-IP>` to the serve command. If the
proxy changes Host or terminates TLS, also add `--allow-origin https://<public-hostname>` (include a
nonstandard port when used). See [Serve options](../reference/cli.md#serve). Binding to `0.0.0.0`
alone does not permit arbitrary browser hosts.

Command actions are disabled in the Docker configuration. Their opt-in setting is documented under
[Actions](../actions.md#commands).

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
