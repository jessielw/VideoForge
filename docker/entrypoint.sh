#!/bin/sh
# LinuxServer-style controls for a container started as root (Unraid's template sets TZ; PUID 99 / PGID 100):
#   TZ:          the container's time zone (log and job record times)
#   PUID / PGID: run as that user and group (set both), as with `docker run --user`. /data (the app's own
#                folder) is handed over first, so a queue made while it ran as root stays usable; your media
#                is left as it is. /tools is made readable (and DEE's Linux programs executable) so it just works.
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
    # Your tools just work: readable by whoever it runs as, and DEE's Linux programs executable. A read-only
    # mount can't be changed (it is copied below instead).
    if [ -d /tools ]; then
        chmod -R a+rX /tools 2>/dev/null || true
        find /tools/dee -maxdepth 1 -type f \( -name dee -o -name 'dee_*_encoder' \) -exec chmod a+x {} + 2>/dev/null || true
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
#   dee:  /tools/dee/dee (the Linux build), else /tools/wine/dee/dee.exe (the Windows build, under Wine);
#         or the split encoders (dee_ddp_encoder, ...): /tools/dee/ (Linux), else /tools/wine/dee/ (Windows, under Wine)
#   qaac: /tools/wine/qaac/qaac64.exe (with its QTfiles64 folder), under Wine
bin="/tmp/videoforge-bin-$(id -u)"
rm -rf "$bin"
mkdir -p "$bin"
launcher() {
    printf '#!/bin/sh\nexec %s "$@"\n' "$2" >"$bin/$1"
    chmod 0755 "$bin/$1"
}
# The Linux DEE folder, as it is, or (if its programs aren't executable and weren't fixed above, e.g. a read-only
# mount) a copy of it of this container's own with them executable. A copy is only disk, made once per start.
dee_dir=/tools/dee
if [ -d /tools/dee ] && [ -n "$(find /tools/dee -maxdepth 1 -type f \( -name dee -o -name 'dee_*_encoder' \) ! -executable -print -quit 2>/dev/null)" ]; then
    stage="/tmp/videoforge-tools-$(id -u)"
    rm -rf "$stage"
    mkdir -p "$stage"
    if cp -R /tools/dee "$stage/dee" 2>/dev/null && chmod -R u+rwx "$stage/dee"; then
        dee_dir="$stage/dee"
    else
        echo "videoforge: /tools/dee can't be read or run by this container: chmod -R a+rX /tools (on the host), or set PUID and PGID" >&2
    fi
fi
if [ -f "$dee_dir/dee" ]; then
    launcher dee "$dee_dir/dee"
elif [ -f /tools/wine/dee/dee.exe ]; then
    launcher dee "/opt/wine/bin/wine-run /tools/wine/dee/dee.exe"
elif [ -f "$dee_dir/dee_ddp_encoder" ]; then
    # split encoders, Linux build: a folder of them, which VideoForge finds by dee_ddp_encoder on PATH
    PATH="$dee_dir:$PATH"
elif [ -f /tools/wine/dee/dee_ddp_encoder.exe ]; then
    # split encoders, Windows build: DeeZy wants extensionless names, so a folder of launchers, one per .exe
    mkdir -p "$bin/dee-split"
    for exe in /tools/wine/dee/dee_*.exe; do
        name="$(basename "$exe" .exe)"
        printf '#!/bin/sh\nexec /opt/wine/bin/wine-run "%s" "$@"\n' "$exe" >"$bin/dee-split/$name"
        chmod 0755 "$bin/dee-split/$name"
    done
    PATH="$bin/dee-split:$PATH"
fi
if [ -f /tools/wine/qaac/qaac64.exe ]; then
    launcher qaac "/opt/wine/bin/wine-run /tools/wine/qaac/qaac64.exe"
fi
if [ -d /tools ] && [ -n "$(find /tools ! -readable -print -quit 2>/dev/null)" ]; then
    echo "videoforge: some files in /tools can't be read by this container: chmod -R a+rX /tools (on the host)" >&2
fi
PATH="$bin:$PATH"
export PATH

# What was found, in the container's log (docker logs): one line per tool.
report() {
    echo "videoforge: $1: $2"
}
if [ -x "$bin/dee" ]; then
    case "$dee_dir" in /tmp/*) report dee "found, run from a copy ($dee_dir): /tools is read-only" ;; *) report dee found ;; esac
elif [ -d "$bin/dee-split" ] || [ -f "$dee_dir/dee_ddp_encoder" ]; then
    report dee "found (split encoders)"
else
    report dee "not in /tools (optional: /tools/dee/dee or /tools/wine/dee/dee.exe)"
fi
if [ -x "$bin/qaac" ]; then
    report qaac "found (Wine)"
else
    report qaac "not in /tools (optional: /tools/wine/qaac/qaac64.exe)"
fi
# Set up Wine's files now, in the background, so the first qaac or DEE run isn't the slow one.
if [ -x "$bin/qaac" ] || { [ -x "$bin/dee" ] && grep -q wine-run "$bin/dee"; } || [ -d "$bin/dee-split" ]; then
    /opt/wine/bin/wine-run --init >/dev/null 2>&1 &
fi
exec "$@"
