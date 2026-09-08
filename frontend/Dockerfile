# DarkNexus interface.
#
# Two stages: Node compiles the bundle, nginx serves it. The build tools do
# not ship - the delivered image is a static bundle behind a web server, which
# is both smaller and has far less in it to attack than a dev server would.
#
# The Vite dev server used in development is not appropriate here: it
# recompiles on every request and exposes the source tree.

FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Empty means "same origin": the bundle calls /api on whatever host serves it,
# and nginx below forwards that to the backend. Left unset, the client falls
# back to http://127.0.0.1:8000 - which, in a browser, is the *user's* machine,
# where nothing is listening. Every request would fail with no obvious cause.
ENV VITE_API_BASE_URL=""
RUN npm run build

# ── Serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
