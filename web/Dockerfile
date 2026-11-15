# 1단계 : 빌드 (Node 와 node_modules 는 여기에만) — 01 「도커만으로 React 앱 (2)」와 같다
FROM node:lts-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2단계 : 서빙 (빌드 결과물 dist/ 만 nginx 로)
FROM nginx:alpine-slim
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
