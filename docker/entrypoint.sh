#!/bin/sh
# PUID / PGID (Unraid's 99 / 100) and UMASK, for a container started as root: the files it writes go to that
# user, as with `docker run --user`. /data (the app's own folder) is handed over first, so a container that ran
# as root before keeps its queue; your media and /tools are left as they are.
if [ "$(id -u)" = 0 ] && [ -n "${PUID:-}" ]; then
    uid="$PUID"
    gid="${PGID:-$PUID}"
    case "$uid$gid" in
    *[!0-9]*)
        echo "videoforge: PUID and PGID must be numeric ids, not '$uid' / '$gid'" >&2
        exit 1
        ;;
    esac
    if [ "$uid" != 0 ]; then
        find /data \( ! -user "$uid" -o ! -group "$gid" \) -exec chown "$uid:$gid" {} +
        unset PUID PGID
        exec python -c 'import os, sys
os.setgroups([])
os.setgid(int(sys.argv[2]))
os.setuid(int(sys.argv[1]))
os.execvp(sys.argv[3], sys.argv[3:])' "$uid" "$gid" "$0" "$@"
    fi
fi
if [ -n "${UMASK:-}" ]; then
    umask "$UMASK" || exit 1
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
