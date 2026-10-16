FROM node:24.15.0-alpine AS build
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web .
# Full tests run with pinned Python in the frontend CI matrix before release.
# The delivery container compiles assets without bundling test runtimes.
RUN npm run format:check && npm run bundle

FROM nginx:1.28.2-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
