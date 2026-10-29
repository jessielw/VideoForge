#!/bin/sh
# LinuxServer-style controls for a container started as root (Unraid's template sets TZ; PUID 99 / PGID 100):
#   TZ:          the container's time zone (log and job record times)
#   PUID / PGID: run as that user and group (set both), as with `docker run --user`. /data (the app's own
#                folder) is handed over first, so a queue made while it ran as root stays usable; your media
#                and /tools are left as they are.
#   UMASK:       the file-creation mask for what it writes (022, 002, 000)
set -eu

fail() {
    echo "videoforge: $*" >&2
    exit 1
}

is_numeric() {
    case "$1" in
    *[!0-9]* | "") return 1 ;;
    *) return 0 ;;
    esac
}

if [ "$(id -u)" = 0 ]; then
    if [ -n "${PUID:-}" ] || [ -n "${PGID:-}" ]; then
        [ -n "${PUID:-}" ] && [ -n "${PGID:-}" ] || fail "PUID and PGID must be set together"
        is_numeric "$PUID" || fail "PUID must be a numeric user id, not '$PUID'"
        is_numeric "$PGID" || fail "PGID must be a numeric group id, not '$PGID'"
    fi
    if [ -n "${TZ:-}" ]; then
        [ -e "/usr/share/zoneinfo/$TZ" ] || fail "TZ '$TZ' is not a time zone in /usr/share/zoneinfo"
        ln -snf "/usr/share/zoneinfo/$TZ" /etc/localtime
        echo "$TZ" >/etc/timezone
    fi
    if [ -n "${PUID:-}" ] && { [ "$PUID" != 0 ] || [ "$PGID" != 0 ]; }; then
        # A named user for the ids (an existing one if the image has it), so gosu sets its groups. A restarted
        # container with other ids renumbers the videoforge user and group it made before.
        group="$(getent group "$PGID" | cut -d: -f1 || true)"
        if [ -z "$group" ]; then
            group=videoforge
            if getent group "$group" >/dev/null; then
                groupmod -o -g "$PGID" "$group"
            else
                groupadd -o -g "$PGID" "$group"
            fi
        fi
        user="$(getent passwd "$PUID" | cut -d: -f1 || true)"
        if [ -n "$user" ]; then
            usermod -g "$PGID" "$user"
        elif getent passwd videoforge >/dev/null; then
            user=videoforge
            usermod -o -u "$PUID" -g "$PGID" "$user"
        else
            user=videoforge
            useradd -o -u "$PUID" -g "$PGID" -d "$HOME" -s /usr/sbin/nologin "$user"
        fi
        find /data \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown "$PUID:$PGID" {} +
        unset PUID PGID
        # gosu sets HOME to the user's own: keep the image's (VapourSynth's config, the Wine prefixes).
        exec gosu "$user:$group" env HOME="$HOME" "$0" "$@"
    fi
fi
if [ -n "${UMASK:-}" ]; then
    case "$UMASK" in
    *[!0-7]* | "" | ?????*) fail "UMASK must be 1-4 octal digits such as 022 or 002, not '$UMASK'" ;;
    esac
    umask "$UMASK"
fi

# Your tools in /tools, found on PATH by the image's config (dee = "dee", qaac = "qaac"): a launcher each in a
# folder of this container's own, only for what's there, so a missing tool shows as missing.
#   dee:  /tools/dee/dee (the Linux build), else /tools/wine/dee/dee.exe (the Windows build, under Wine)
#   qaac: /tools/wine/qaac/qaac64.exe (with its QTfiles64 folder), under Wine
bin="/tmp/videoforge-bin-$(id -u)"
rm -rf "$bin"
mkdir -p "$bin"
launcher() {
    printf '#!/bin/sh\nexec %s "$@"\n' "$2" >"$bin/$1"
    chmod 0755 "$bin/$1"
}
if [ -f /tools/dee/dee ]; then
    launcher dee /tools/dee/dee
    [ -x /tools/dee/dee ] || echo "videoforge: /tools/dee/dee can't run: chmod +x /tools/dee/* (on the host)" >&2
elif [ -f /tools/wine/dee/dee.exe ]; then
    launcher dee "/opt/wine/bin/wine-run /tools/wine/dee/dee.exe"
fi
if [ -f /tools/wine/qaac/qaac64.exe ]; then
    launcher qaac "/opt/wine/bin/wine-run /tools/wine/qaac/qaac64.exe"
fi
PATH="$bin:$PATH"
export PATH
exec "$@"
