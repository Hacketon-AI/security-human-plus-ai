# deps: install with Bun on the official pinned, glibc (non-Alpine) image.
# Alpine/musl was the root cause of the @unrs/resolver-binding-linux-x64-musl
# integrity failure (napi native binding built for musl vs. glibc mismatch).
FROM oven/bun:1.3.14 AS deps
WORKDIR /app
COPY package.json bun.lock ./
# Retry up to 3x on transient registry/integrity failures, clearing Bun's
# package cache between attempts so a corrupted tarball isn't reused.
RUN for attempt in 1 2 3; do \
      bun install --frozen-lockfile && exit 0; \
      echo "bun install failed (attempt $attempt/3)"; \
      bun pm cache rm; \
    done; \
    echo "bun install failed after 3 attempts" && exit 1

FROM oven/bun:1.3.14 AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN bun run build

# runner: glibc runtime for the Next.js standalone output
FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# The build script already copies .next/static and public into standalone
COPY --from=builder /app/.next/standalone ./

EXPOSE 3000
CMD ["node", "server.js"]
