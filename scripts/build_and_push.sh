#!/bin/bash
#
# Build and push Continuum Docker images to ECR
#

set -e

export AWS_REGION=${AWS_REGION:-us-east-1}
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export ECR=$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

echo "🔨 Building Continuum Docker Images"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "AWS Account: $AWS_ACCOUNT"
echo "Region: $AWS_REGION"
echo "ECR: $ECR"
echo ""

# Create ECR repos if they don't exist
echo "📦 Creating ECR repositories..."
aws ecr create-repository --repository-name keep-backend --region $AWS_REGION > /dev/null 2>&1 && echo "  ✓ keep-backend repo created" || echo "  ✓ keep-backend repo exists"
aws ecr create-repository --repository-name keep-frontend --region $AWS_REGION > /dev/null 2>&1 && echo "  ✓ keep-frontend repo created" || echo "  ✓ keep-frontend repo exists"
echo ""

# Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR
echo "✓ Logged in"
echo ""

# Build backend
echo "🏗️  Building backend image (this may take 3-5 minutes)..."
echo "   Stage 1: Setting up Python environment..."
echo "   Stage 2: Installing dependencies..."
echo "   Stage 3: Copying application files..."
docker build -f docker/Dockerfile.api -t keep-backend:latest . --progress=plain 2>&1 | \
  while IFS= read -r line; do
    echo "$line" | grep -E "^#[0-9]+ \[" && echo "   $line" || true
  done
echo "✓ Backend built"
echo ""

# Build frontend
echo "🏗️  Building frontend image..."
echo ""
echo "⚠️  Frontend build requires 4-6 GB Docker memory"
echo "   If this fails with 'cannot allocate memory', either:"
echo "   1. Increase Docker Desktop memory (Settings → Resources → Memory)"
echo "   2. Or run: ./scripts/build_frontend_local.sh (faster alternative)"
echo ""
echo "   Building... (this may take 5-10 minutes)"

if docker build -f docker/Dockerfile.ui -t keep-frontend:latest ./keep-ui 2>&1 | \
   tee /tmp/docker-build-frontend.log | \
   grep --line-buffered -E "^\#[0-9]+ |FINISHED|exporting" | \
   sed 's/^/   /'; then
  echo "✓ Frontend built"
else
  echo ""
  echo "❌ Frontend build failed (likely out of memory)"
  echo ""
  echo "Run this instead:"
  echo "  ./scripts/build_frontend_local.sh"
  echo ""
  exit 1
fi
echo ""

# Tag images
echo "🏷️  Tagging images..."
docker tag keep-backend:latest $ECR/keep-backend:latest
docker tag keep-frontend:latest $ECR/keep-frontend:latest
echo "✓ Images tagged"
echo ""

# Push to ECR
echo "📤 Pushing backend to ECR..."
docker push $ECR/keep-backend:latest
echo "✓ Backend pushed"

echo "📤 Pushing frontend to ECR..."
docker push $ECR/keep-frontend:latest
echo "✓ Frontend pushed"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Images built and pushed successfully!"
echo ""
echo "Backend: $ECR/keep-backend:latest"
echo "Frontend: $ECR/keep-frontend:latest"
echo ""
echo "Next: Deploy with CloudFormation"
echo "  ./scripts/deploy_cloudformation.sh"

