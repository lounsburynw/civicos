FROM node:20-slim

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production

# Copy source
COPY . .

# Build widgets
RUN npm run build

# Expose port
EXPOSE 3002

# Start server
CMD ["npm", "run", "serve"]
