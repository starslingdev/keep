#!/bin/bash
#
# Deploy Keep with AI Remediation to AWS ECS
# Usage: ./deploy_aws_ecs.sh [environment]
# Example: ./deploy_aws_ecs.sh prod
#

set -e

ENVIRONMENT="${1:-prod}"
REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$AWS_ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
CLUSTER="keep-$ENVIRONMENT"

echo "🚀 Deploying Keep to AWS ECS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Cluster: $CLUSTER"
echo "ECR: $ECR_REPO"
echo ""

# Check required environment variables
echo "✓ Checking prerequisites..."
if [ -z "$GITHUB_APP_ID" ]; then
    echo "❌ GITHUB_APP_ID not set"
    exit 1
fi

if [ -z "$GITHUB_PRIVATE_KEY_PATH" ] && [ -z "$GITHUB_PRIVATE_KEY" ]; then
    echo "❌ GITHUB_PRIVATE_KEY_PATH or GITHUB_PRIVATE_KEY not set"
    exit 1
fi

echo "✓ Prerequisites OK"
echo ""

# Step 1: Login to ECR
echo "🔐 Logging into ECR..."
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin $ECR_REPO
echo "✓ ECR login successful"
echo ""

# Step 2: Build images
echo "🔨 Building Docker images..."
docker build -f docker/Dockerfile.api -t keep-backend:$ENVIRONMENT .
docker build -f docker/Dockerfile.ui -t keep-frontend:$ENVIRONMENT ./keep-ui
echo "✓ Images built successfully"
echo ""

# Step 3: Tag images
echo "🏷️  Tagging images..."
docker tag keep-backend:$ENVIRONMENT $ECR_REPO/keep-backend:$ENVIRONMENT
docker tag keep-backend:$ENVIRONMENT $ECR_REPO/keep-backend:latest
docker tag keep-frontend:$ENVIRONMENT $ECR_REPO/keep-frontend:$ENVIRONMENT
docker tag keep-frontend:$ENVIRONMENT $ECR_REPO/keep-frontend:latest
echo "✓ Images tagged"
echo ""

# Step 4: Push to ECR
echo "📤 Pushing images to ECR..."
docker push $ECR_REPO/keep-backend:$ENVIRONMENT
docker push $ECR_REPO/keep-backend:latest
docker push $ECR_REPO/keep-frontend:$ENVIRONMENT
docker push $ECR_REPO/keep-frontend:latest
echo "✓ Images pushed successfully"
echo ""

# Step 5: Update ECS services
echo "🔄 Updating ECS services..."

# Update backend API
aws ecs update-service \
    --cluster $CLUSTER \
    --service keep-backend-api \
    --force-new-deployment \
    --region $REGION > /dev/null

echo "✓ Backend API deployment triggered"

# Update ARQ workers
aws ecs update-service \
    --cluster $CLUSTER \
    --service keep-arq-workers \
    --force-new-deployment \
    --region $REGION > /dev/null

echo "✓ ARQ workers deployment triggered"

# Update frontend
aws ecs update-service \
    --cluster $CLUSTER \
    --service keep-frontend \
    --force-new-deployment \
    --region $REGION > /dev/null

echo "✓ Frontend deployment triggered"
echo ""

# Step 6: Wait for stability
echo "⏳ Waiting for services to stabilize..."
echo "(This may take 5-10 minutes...)"

aws ecs wait services-stable \
    --cluster $CLUSTER \
    --services keep-backend-api keep-arq-workers keep-frontend \
    --region $REGION

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment completed successfully!"
echo ""
echo "📋 Next steps:"
echo "  1. Test signup: curl https://yourkeep.com/api/public/signup"
echo "  2. Check logs: aws logs tail /ecs/keep-backend --follow"
echo "  3. Monitor: CloudWatch dashboard"
echo ""
echo "🎉 Your AI Remediation feature is live!"

