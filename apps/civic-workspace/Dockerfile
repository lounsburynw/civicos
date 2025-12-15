# Civic Frontend - Docker Image
# Multi-stage build: Node.js build -> nginx serve

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Build for production
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine AS runtime

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration (if exists)
# COPY nginx.conf /etc/nginx/nginx.conf

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
