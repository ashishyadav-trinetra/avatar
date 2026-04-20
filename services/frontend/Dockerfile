# ── Build stage ───────────────────────────────────────────────
FROM node:20-alpine AS builder

ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000
ARG VITE_WEBRTC_URL=http://localhost:8002

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
ENV VITE_WEBRTC_URL=$VITE_WEBRTC_URL

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── Serve stage ───────────────────────────────────────────────
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
