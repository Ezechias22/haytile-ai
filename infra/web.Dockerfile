FROM node:24-slim AS build
WORKDIR /app/apps/web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
COPY packages/ /app/packages/
RUN npm run build
ENV NODE_ENV=production
USER node
EXPOSE 3000
CMD ["npm","run","start"]
