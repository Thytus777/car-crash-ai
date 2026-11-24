# syntax=docker/dockerfile:1
# The web app as a standalone Next.js server. The base image is pinned by
# digest; Dependabot proposes updates weekly.
ARG NODE_IMAGE=node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5

# --- build ------------------------------------------------------------------
FROM ${NODE_IMAGE} AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# --- runtime: only the standalone server, non-root ---------------------------
FROM ${NODE_IMAGE} AS runtime
# Apply Alpine security fixes (the pinned base can lag; Trivy gates the result).
RUN apk upgrade --no-cache \
    && addgroup -S -g 10001 app && adduser -S -u 10001 -G app app \
    # npm isn't needed to run the server, and its bundled packages are the
    # usual source of scanner findings.
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 HOSTNAME=0.0.0.0
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
USER 10001
EXPOSE 8080
CMD ["node", "server.js"]
