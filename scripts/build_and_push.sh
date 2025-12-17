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

# Build backend for linux/amd64 (required for ECS Fargate)
echo "🏗️  Building backend image for linux/amd64 platform..."
echo "   (Building for ECS Fargate - this may take 5-10 minutes on Apple Silicon)"
docker build \
  --platform linux/amd64 \
  -f docker/Dockerfile.api \
  -t keep-backend:latest \
  . 
echo "✓ Backend built for linux/amd64"
echo ""

# Build frontend for linux/amd64 (required for ECS Fargate)
echo "🏗️  Building frontend image for linux/amd64 platform..."
echo "   (Building for ECS Fargate - this may take 5-10 minutes on Apple Silicon)"
docker build \
  --platform linux/amd64 \
  -f docker/Dockerfile.ui \
  -t keep-frontend:latest \
  ./keep-ui
echo "✓ Frontend built for linux/amd64"
echo ""

# Tag images
echo "🏷️  Tagging images..."
docker tag keep-backend:latest $ECR/keep-backend:latest
docker tag keep-frontend:latest $ECR/keep-frontend:latest
echo "✓ Images tagged"
echo ""

# Push to ECR with retries
echo "📤 Pushing backend to ECR (large image, may take 5-10 min)..."
for i in {1..100}; do
  if docker push $ECR/keep-backend:latest; then
    echo "✓ Backend pushed"
    break
  else
    echo "⚠️  Push failed, retrying ($i/3)..."
    sleep 5
  fi
done

echo "📤 Pushing frontend to ECR..."
for i in {1..3}; do
  if docker push $ECR/keep-frontend:latest; then
    echo "✓ Frontend pushed"
    break
  else
    echo "⚠️  Push failed, retrying ($i/3)..."
    sleep 5
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Images built and pushed successfully!"
echo ""
echo "Backend: $ECR/keep-backend:latest"
echo "Frontend: $ECR/keep-frontend:latest"
echo ""
echo "Next: Deploy with CloudFormation"
echo "  ./scripts/deploy_cloudformation.sh"

