# Tor daemon for hidden-service collection.
#
# Separate from the backend on purpose: the anonymity layer and the collector
# have different lifecycles. Tor needs to bootstrap a circuit before it is
# useful, and rotating a circuit should not mean restarting the application.
FROM alpine:3.20

RUN apk add --no-cache tor curl

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && chown -R tor:root /var/lib/tor

USER tor

EXPOSE 9050 9051

# Bootstrapping takes time, and a container that is up but has no circuit
# cannot serve a request - so health is "can this actually reach Tor", not
# "is the port open".
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -sf --socks5-hostname 127.0.0.1:9050 \
        https://check.torproject.org/api/ip | grep -q '"IsTor":true' || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
