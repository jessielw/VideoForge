#!/bin/bash
# Builds the image's template Wine prefix (/opt/wine-prefix), which the qaac wrapper copies for each user id.
# Its DLLs are copies of Wine's own: they become links into Wine, so a copy of the prefix is small and quick.
set -euo pipefail
prefix=/opt/wine-prefix
lib=/usr/lib/x86_64-linux-gnu/wine
export WINEPREFIX="$prefix" WINEDEBUG=-all
/usr/lib/wine/wine64 wineboot -i >/dev/null 2>&1
/usr/lib/wine/wineserver -w
linked=0
while IFS= read -r -d '' f; do
    name="$(basename "$f")"
    for src in "$lib/x86_64-windows/$name" "$lib/i386-windows/$name"; do
        if [ -f "$src" ] && cmp -s "$f" "$src"; then
            ln -sf "$src" "$f"
            linked=$((linked + 1))
            break
        fi
    done
done < <(find "$prefix/drive_c/windows" -type f -print0)
chmod -R a+rX "$prefix"
echo "wine prefix: $linked files linked, $(du -sh "$prefix" | cut -f1)"
