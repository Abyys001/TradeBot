# Build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --fetch-retries 10 --fetch-retry-mintimeout 20000 --fetch-retry-maxtimeout 180000 --fetch-timeout 600000
COPY . .
RUN npm run build

# Serve via nginx (proxies /api and /ws to Django)
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
