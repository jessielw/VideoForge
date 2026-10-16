#!/bin/sh
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
