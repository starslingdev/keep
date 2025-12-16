#!/bin/bash
#
# Build frontend locally (workaround for Docker memory issues)
#

set -e

echo "🏗️  Building frontend locally (faster and avoids Docker memory issues)..."
cd keep-ui

# Build Next.js
echo "   Installing dependencies..."
npm install --silent

echo "   Building Next.js application..."
SENTRY_DISABLED=true KEEP_INCLUDE_SOURCES=false npm run build

cd ..

echo "✓ Frontend built successfully"
echo ""
echo "Now building Docker image with pre-built files..."

# Create lightweight Dockerfile that just copies built files
cat > docker/Dockerfile.ui.local << 'EOF'
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy the standalone build
COPY keep-ui/.next/standalone ./
COPY keep-ui/.next/static ./.next/static
COPY keep-ui/public ./public

USER nextjs

EXPOSE 3000
ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

CMD ["node", "server.js"]
EOF

docker build -f docker/Dockerfile.ui.local -t keep-frontend:latest .
rm docker/Dockerfile.ui.local

echo "✓ Docker image created"
echo ""
echo "Frontend image ready: keep-frontend:latest"

