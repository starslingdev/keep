# Deploy Continuum to AWS - Complete Guide

## One-Command Deployment

```bash
# 1. Build and push images (5 min)
./scripts/build_and_push.sh

# 2. Deploy infrastructure (10 min)
./scripts/deploy_cloudformation.sh

# 3. Get your URL
aws cloudformation describe-stacks \
  --stack-name continuum-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`SignupURL`].OutputValue' \
  --output text

# Share that URL with customers!
```

## Prerequisites

- AWS CLI configured (`aws configure`)
- Docker installed
- ~20 minutes

## Detailed Steps

### Step 1: Create ECR Repositories (One-Time)

```bash
aws ecr create-repository --repository-name keep-backend --region us-east-1
aws ecr create-repository --repository-name keep-frontend --region us-east-1
```

### Step 2: Build & Push Docker Images

```bash
cd /Users/ali/Projects/keep

# Get AWS account ID
export AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
export ECR=$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR

# Build images
docker build -f docker/Dockerfile.api -t keep-backend:latest .
docker build -f docker/Dockerfile.ui -t keep-frontend:latest ./keep-ui

# Tag images
docker tag keep-backend:latest $ECR/keep-backend:latest
docker tag keep-frontend:latest $ECR/keep-frontend:latest

# Push to ECR
docker push $ECR/keep-backend:latest
docker push $ECR/keep-frontend:latest
```

### Step 3: Deploy with CloudFormation

```bash
aws cloudformation deploy \
  --template-file aws-cloudformation.yaml \
  --stack-name continuum-prod \
  --parameter-overrides \
      Environment=prod \
      DatabasePassword=YourSecurePassword123! \
      GitHubAppId="" \
      SentryAuthToken="" \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

This creates:
- ✅ VPC with public/private subnets
- ✅ RDS PostgreSQL (db.t4g.micro)
- ✅ ElastiCache Redis (cache.t4g.micro)
- ✅ Application Load Balancer
- ✅ ECS Cluster + 3 Services (backend, worker, frontend)
- ✅ Security groups
- ✅ IAM roles

**Time**: ~10-15 minutes

### Step 4: Get Your URLs

```bash
# Get signup URL
aws cloudformation describe-stacks \
  --stack-name continuum-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`SignupURL`].OutputValue' \
  --output text

# Example output:
# http://prod-continuum-alb-1234567890.us-east-1.elb.amazonaws.com/signup
```

### Step 5: Test Signup

Visit the signup URL and create an account!

## Updates & Redeployment

When you make code changes:

```bash
# 1. Rebuild and push images
docker build -f docker/Dockerfile.api -t $ECR/keep-backend:latest .
docker push $ECR/keep-backend:latest

# 2. Force ECS to redeploy
aws ecs update-service \
  --cluster prod-continuum \
  --service prod-continuum-backend \
  --force-new-deployment

aws ecs update-service \
  --cluster prod-continuum \
  --service prod-continuum-worker \
  --force-new-deployment
```

## Configuration

### Enable Features via CloudFormation Update

```bash
# Enable GitHub PR creation later
aws cloudformation update-stack \
  --stack-name continuum-prod \
  --use-previous-template \
  --parameters \
      ParameterKey=Environment,UsePreviousValue=true \
      ParameterKey=DatabasePassword,UsePreviousValue=true \
      ParameterKey=GitHubAppId,ParameterValue=123456 \
      ParameterKey=SentryAuthToken,UsePreviousValue=true
```

### Monitor Deployment

```bash
# Watch CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name continuum-prod \
  --max-items 20

# Watch ECS service status
aws ecs describe-services \
  --cluster prod-continuum \
  --services prod-continuum-backend \
  --query 'services[0].events[0:5]'

# View logs
aws logs tail /ecs/prod-continuum-backend --follow
```

## Costs

| Resource | Type | Monthly Cost |
|----------|------|--------------|
| ECS Backend | 1 task × 0.5 vCPU, 1 GB | ~$15 |
| ECS Worker | 1 task × 0.5 vCPU, 1 GB | ~$15 |
| ECS Frontend | 1 task × 0.25 vCPU, 0.5 GB | ~$8 |
| RDS PostgreSQL | db.t4g.micro | ~$15 |
| ElastiCache Redis | cache.t4g.micro | ~$12 |
| ALB | Standard | ~$20 |
| Data Transfer | ~50 GB | ~$5 |
| **Total** | | **~$90/month** |

## Teardown (Delete Everything)

```bash
# Delete stack
aws cloudformation delete-stack --stack-name continuum-prod

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name continuum-prod

echo "✅ All resources deleted"
```

## Troubleshooting

### Stack Creation Failed

```bash
# Check why
aws cloudformation describe-stack-events \
  --stack-name continuum-prod \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'
```

### Service Won't Start

```bash
# Check task failures
aws ecs describe-tasks \
  --cluster prod-continuum \
  --tasks $(aws ecs list-tasks --cluster prod-continuum --service-name prod-continuum-backend --query 'taskArns[0]' --output text) \
  --query 'tasks[0].containers[0].reason'

# Check logs
aws logs tail /ecs/prod-continuum-backend --follow
```

### Can't Access Signup Page

1. Check ALB is healthy: Visit the LoadBalancerURL from outputs
2. Check security groups allow port 80
3. Check ECS tasks are running: `aws ecs list-tasks --cluster prod-continuum`

---

## Complete Deployment (Copy-Paste)

```bash
#!/bin/bash
set -e

cd /Users/ali/Projects/keep

echo "🚀 Complete Continuum Deployment to AWS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Build and push images FIRST
echo "Step 1: Building and pushing Docker images..."
./scripts/build_and_push.sh

# 2. Deploy infrastructure
echo ""
echo "Step 2: Deploying CloudFormation stack..."
export DB_PASSWORD="Keep$(openssl rand -base64 12 | tr -d '/+=')!"
echo "Database password: $DB_PASSWORD"
echo "(Save this!)"
echo ""

./scripts/deploy_cloudformation.sh

# 3. Done!
echo ""
echo "✅ Deployment complete!"
aws cloudformation describe-stacks \
  --stack-name continuum-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`SignupURL`].OutputValue' \
  --output text
```

**Critical**: Images must be in ECR BEFORE CloudFormation runs!

