#!/bin/sh
# qaac runs under Wine (the wrapper in /opt/qaac/bin) when qaac64.exe is mounted; otherwise "qaac" isn't on
# PATH, so AAC (qaac) shows as unavailable.
if [ -f "${QAAC_DIR:-/tools/qaac}/qaac64.exe" ]; then
    PATH="/opt/qaac/bin:$PATH"
    export PATH
fi
exec "$@"
