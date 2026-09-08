#!/bin/sh
set -e

# The control password is hashed at start-up from an environment variable
# rather than baked into the image. A torrc committed with a real hash in it
# is a credential in source control, and the whole point of the control port
# is that only this application may rotate circuits.
if [ -z "$TOR_CONTROL_PASSWORD" ]; then
    echo "TOR_CONTROL_PASSWORD is not set; circuit rotation will be unavailable." >&2
    CONTROL_LINE=""
else
    HASHED=$(tor --hash-password "$TOR_CONTROL_PASSWORD" | tail -n 1)
    CONTROL_LINE="ControlPort 0.0.0.0:9051
HashedControlPassword $HASHED"
fi

cat > /tmp/torrc <<TORRC
# Bound to all interfaces because the collector reaches this from another
# container. Nothing outside the compose network can reach it: neither port
# is published to the host.
SocksPort 0.0.0.0:9050
$CONTROL_LINE

DataDirectory /var/lib/tor
Log notice stdout

# Collection is many short fetches of different services; letting circuits
# live a little longer avoids rebuilding one per request.
MaxCircuitDirtiness 600
TORRC

exec tor -f /tmp/torrc
