# =============================
# Base Image
# =============================

FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN npm ci

# =============================
# Development Image
# =============================

FROM base AS dev
EXPOSE 4200
CMD ["npm", "run", "start", "--", "--host", "0.0.0.0", "--poll=2000"]

# =============================
# Production Image
# =============================

FROM base AS prod
COPY . .
RUN npm run build
EXPOSE 80
RUN npm install -g serve
CMD ["serve", "-s", "dist/raidmetrics-portal/browser", "-l", "80"]