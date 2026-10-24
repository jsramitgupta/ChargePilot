FROM node:24.22.1-bookworm-slim AS dependencies
WORKDIR /opt/app
COPY package.json package-lock.json ./
COPY patches ./patches
RUN npm ci

FROM node:24.22.1-bookworm-slim AS builder
WORKDIR /opt/app
ENV DATABASE_CLIENT=postgres \
    DATABASE_HOST=127.0.0.1 \
    DATABASE_PORT=5432 \
    DATABASE_NAME=chargepilot_docs \
    DATABASE_USERNAME=chargepilot_docs \
    DATABASE_PASSWORD=build-only-not-a-secret \
    APP_KEYS=build-one,build-two,build-three,build-four \
    ADMIN_JWT_SECRET=build-only-not-a-secret \
    API_TOKEN_SALT=build-only-not-a-secret \
    TRANSFER_TOKEN_SALT=build-only-not-a-secret \
    ENCRYPTION_KEY=build-only-not-a-secret \
    JWT_SECRET=build-only-not-a-secret
COPY --from=dependencies /opt/app/node_modules ./node_modules
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:24.22.1-bookworm-slim AS runner
WORKDIR /opt/app
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=1337 \
    STRAPI_TELEMETRY_DISABLED=true
RUN groupadd --system --gid 10001 strapi \
    && useradd --system --uid 10001 --gid strapi strapi
COPY --from=builder --chown=strapi:strapi /opt/app ./
USER 10001:10001
EXPOSE 1337
CMD ["npm", "run", "start"]
