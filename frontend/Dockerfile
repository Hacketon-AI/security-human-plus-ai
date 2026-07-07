FROM node:20-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

FROM base AS builder
COPY package.json package-lock.json* bun.lock* ./
# Install dependencies
RUN if [ -f package-lock.json ]; then npm ci; \
    elif [ -f bun.lock ]; then npm install -g bun && bun install; \
    else npm install; \
    fi

COPY . .
# Pass build-time variables if needed
RUN npm run build

FROM base AS runner
ENV NODE_ENV=production
ENV PORT=3000

# The build script already copies .next/static and public into standalone
COPY --from=builder /app/.next/standalone ./

EXPOSE 3000
CMD ["node", "server.js"]
