# ==================== Frontend Dockerfile ====================
# Stages: deps (npm ci, cached) → dev (CRA dev server, used by docker-compose.override.yml)
#                               → build (production bundle) → nginx (served, the default target)

# -------- deps --------
# Node 24 = Vercel's production Node.js Version and CI's; keep all three in sync.
FROM node:24-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --silent

# -------- dev: hot-reloading dev server; source is bind-mounted over /app --------
FROM deps AS dev
EXPOSE 3000
CMD ["npm", "start"]

# -------- build --------
FROM deps AS build
COPY . .
# Real environment variables override .env.production in CRA, so this picks the API the bundle
# talks to. A build ARG is visible to RUN only when passed; not passed, it stays unset and
# .env.production (the Render URL) applies. No ENV: an empty ENV would still beat the file.
ARG REACT_APP_API_URL
RUN npm run build

# -------- serve with nginx --------
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
