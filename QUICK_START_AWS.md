# Quick Start: Deploy to AWS (No Custom Domain Needed)

## TL;DR

Deploy Keep with AI Remediation to AWS in ~30 minutes using AWS-generated URLs.

## What You'll Get

After deployment, AWS generates URLs for you:

```
Application Load Balancer DNS:
keep-prod-alb-1234567890.us-east-1.elb.amazonaws.com

Your URLs:
├── Signup:  http://keep-prod-alb-....elb.amazonaws.com/signup
├── Login:   http://keep-prod-alb-....elb.amazonaws.com/signin
└── App:     http://keep-prod-alb-....elb.amazonaws.com/
```

No domain registration needed! Use these URLs to get started.

## Prerequisites

- AWS Account
- AWS CLI configured (`aws configure`)
- Docker installed locally
- GitHub App created (App ID + private key file)

## Step-by-Step Deployment

### 1. Store Secrets (2 minutes)

```bash
cd /Users/ali/Projects/keep

# Store GitHub App secrets
aws secretsmanager create-secret \
  --name keep/prod/github-app-id \
  --secret-string "$GITHUB_APP_ID" \
  --region us-east-1

aws secretsmanager create-secret \
  --name keep/prod/github-private-key \
  --secret-string file://path/to/github-key.pem \
  --region us-east-1

# Store database URL (create RDS first, or use placeholder)
aws secretsmanager create-secret \
  --name keep/prod/database-url \
  --secret-string "postgresql://user:pass@your-rds-endpoint:5432/keep" \
  --region us-east-1
```

### 2. Create ECR Repositories (1 minute)

```bash
# Create repos for images
aws ecr create-repository --repository-name keep-backend --region us-east-1
aws ecr create-repository --repository-name keep-frontend --region us-east-1
```

### 3. Build & Push Images (5 minutes)

```bash
# Get your AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com"

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_REPO

# Build and push backend
docker build -f docker/Dockerfile.api -t $ECR_REPO/keep-backend:latest .
docker push $ECR_REPO/keep-backend:latest

# Build and push frontend
docker build -f docker/Dockerfile.ui -t $ECR_REPO/keep-frontend:latest ./keep-ui
docker push $ECR_REPO/keep-frontend:latest
```

### 4. Create Infrastructure (10 minutes)

Use AWS Console or CloudFormation to create:

**VPC & Networking**:
- VPC with 2 public + 2 private subnets
- Internet Gateway
- NAT Gateway (or use public subnets for cost savings)
- Security Groups

**Database**:
- RDS PostgreSQL (db.t4g.micro)
- In private subnet
- Security group allows 5432 from ECS

**Redis**:
- ElastiCache Redis (cache.t4g.micro)
- In private subnet  
- Security group allows 6379 from ECS

**Load Balancer**:
- Application Load Balancer (ALB)
- In public subnets
- Target groups for backend (port 8080) and frontend (port 3000)
- Listener rules:
  - Path `/api/*` → backend target group
  - Path `/*` → frontend target group

### 5. Create ECS Cluster (1 minute)

```bash
aws ecs create-cluster --cluster-name keep-prod --region us-east-1
```

### 6. Register Task Definitions (5 minutes)

Save these to files and register:

**backend-task.json**:
```json
{
  "family": "keep-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT:role/ecsTaskExecutionRole",
  "containerDefinitions": [{
    "name": "keep-backend",
    "image": "YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/keep-backend:latest",
    "portMappings": [{"containerPort": 8080}],
    "environment": [
      {"name": "KEEP_ENABLE_AI_REMEDIATION", "value": "true"},
      {"name": "REDIS", "value": "true"},
      {"name": "REDIS_HOST", "value": "YOUR_REDIS_ENDPOINT"},
      {"name": "AUTH_TYPE", "value": "db"}
    ],
    "secrets": [
      {"name": "DATABASE_CONNECTION_STRING", "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT:secret:keep/prod/database-url"},
      {"name": "GITHUB_APP_ID", "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT:secret:keep/prod/github-app-id"},
      {"name": "GITHUB_PRIVATE_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT:secret:keep/prod/github-private-key"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/keep-backend",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "ecs"
      }
    }
  }]
}
```

Register it:
```bash
aws ecs register-task-definition --cli-input-json file://backend-task.json
```

Repeat for worker and frontend (see full task definitions in `AWS_DEPLOYMENT_WITH_SIGNUP.md`).

### 7. Create ECS Services (3 minutes)

```bash
# Backend API
aws ecs create-service \
  --cluster keep-prod \
  --service-name keep-backend \
  --task-definition keep-backend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=keep-backend,containerPort=8080"

# Workers
aws ecs create-service \
  --cluster keep-prod \
  --service-name keep-workers \
  --task-definition keep-worker \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx]}"

# Frontend
aws ecs create-service \
  --cluster keep-prod \
  --service-name keep-frontend \
  --task-definition keep-frontend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=keep-frontend,containerPort=3000"
```

### 8. Get Your URLs

```bash
# Get ALB DNS name
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names keep-prod-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your Keep instance is available at:"
echo "  🌐 Frontend:  http://$ALB_DNS"
echo "  🔌 API:       http://$ALB_DNS/api"
echo "  📝 Signup:    http://$ALB_DNS/signup"
echo ""
echo "Share the signup URL with your first customers!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

## Testing Your Deployment

### Test Signup

```bash
# Replace with your actual ALB DNS
ALB_DNS="keep-prod-alb-1234567890.us-east-1.elb.amazonaws.com"

curl -X POST "http://$ALB_DNS/api/public/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "organization_name": "Test Company"
  }'
```

Expected response:
```json
{
  "tenant_id": "uuid-...",
  "organization_name": "Test Company",
  "email": "test@example.com",
  "password": "RandomGeneratedPassword123",
  "login_url": "http://keep-prod-alb-....elb.amazonaws.com/signin?tenant=uuid",
  "message": "Account created successfully!"
}
```

### Test Login

Visit the `login_url` from the response and login!

## Cost-Saving Tips

**For MVP / Low Traffic**:

1. **Start small**:
   - 1 backend task (not 2)
   - 1 worker task
   - 1 frontend task
   - db.t4g.micro RDS
   - cache.t4g.micro Redis

   **Cost: ~$70/month**

2. **No NAT Gateway**:
   - Use public subnets for ECS tasks
   - Assign public IPs
   - Save $32/month per NAT Gateway

3. **Spot instances**:
   - Use Fargate Spot for workers
   - Save 70% on worker costs

4. **Single AZ**:
   - Deploy in one availability zone
   - Lower data transfer costs
   - Good for MVP, not production

## Minimal MVP Deployment

If you just want to test with minimal cost:

```bash
# Skip Redis - use background tasks
# 1 backend task only
# RDS smallest instance

Minimal cost: ~$40/month
```

Configuration:
- Remove Redis from task definition
- Set `REDIS=false`
- Background tasks run in-process (less scalable but works)

## When You Grow

**10 customers → Scale to**:
- 2 backend tasks
- 2 worker tasks  
- 2 frontend tasks
- Cost: ~$130/month

**100 customers → Scale to**:
- Auto-scaling (2-10 tasks)
- db.t4g.small RDS
- cache.t4g.small Redis
- Cost: ~$300/month

**1000 customers → Scale to**:
- Auto-scaling (5-50 tasks)
- Aurora PostgreSQL
- Redis cluster
- Cost: ~$1500/month

## Share Your Signup URL

Once deployed, share this URL to get customers:

```
http://keep-prod-alb-1234567890.us-east-1.elb.amazonaws.com/signup
```

**Pro tip**: Use a link shortener for cleaner sharing:
- bitly.com → `bit.ly/keep-ai-signup`
- Make it easier to remember and share!

---

## Next: Get Your First Customer

1. ✅ Deploy to AWS (use commands above)
2. ✅ Get ALB DNS name
3. ✅ Test signup yourself
4. ✅ Share signup URL with a friend/colleague
5. ✅ Watch them create their first AI-generated PR!

**You're ready to launch!** 🚀

