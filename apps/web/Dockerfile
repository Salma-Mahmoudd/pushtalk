# Stage 1: Node + Vite build the static app.
FROM node:24-alpine AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
ARG VITE_SITE_URL=http://localhost:8080
ENV VITE_SITE_URL=$VITE_SITE_URL
RUN pnpm build

# Stage 2: only nginx and the built files (no Node, no source).
FROM nginx:1.30-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
