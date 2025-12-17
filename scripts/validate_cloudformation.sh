#!/bin/bash
#
# Quick validation checks for CloudFormation template
#

set -e

TEMPLATE="aws-cloudformation.yaml"
REGION=${AWS_REGION:-us-east-1}

echo "🔍 Validating CloudFormation Template"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. AWS validation (includes syntax check)
echo "1. Validating template with AWS..."
if aws cloudformation validate-template --template-body file://$TEMPLATE --region $REGION >/dev/null 2>&1; then
  echo "   ✓ AWS validation passed"
else
  echo "   ✗ AWS validation failed"
  aws cloudformation validate-template --template-body file://$TEMPLATE --region $REGION 2>&1 | grep -i error
  exit 1
fi

# 2. Check PostgreSQL version availability
echo "2. Checking PostgreSQL version availability in $REGION..."
PG_VERSION=$(grep -A2 "Engine: postgres" $TEMPLATE | grep "EngineVersion:" | sed "s/.*'\(.*\)'.*/\1/" | tr -d ' ')
AVAILABLE=$(aws rds describe-db-engine-versions \
  --engine postgres \
  --engine-version $PG_VERSION \
  --region $REGION \
  --query 'DBEngineVersions[0].EngineVersion' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$AVAILABLE" != "NOT_FOUND" ] && [ "$AVAILABLE" != "None" ] && [ ! -z "$AVAILABLE" ]; then
  echo "   ✓ PostgreSQL $PG_VERSION available in $REGION"
else
  echo "   ✗ PostgreSQL $PG_VERSION NOT available in $REGION"
  echo "   Available versions:"
  aws rds describe-db-engine-versions \
    --engine postgres \
    --region $REGION \
    --query 'DBEngineVersions[?starts_with(EngineVersion, `15.`)].EngineVersion' \
    --output text | tr '\t' '\n' | sort -V | tail -5
  exit 1
fi

# 3. Check ECR images exist
echo "3. Checking if Docker images exist in ECR..."
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="$AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

for IMAGE in keep-backend keep-frontend; do
  if aws ecr describe-images --repository-name $IMAGE --region $REGION --image-ids imageTag=latest >/dev/null 2>&1; then
    echo "   ✓ $IMAGE:latest exists in ECR"
  else
    echo "   ✗ $IMAGE:latest NOT found in ECR"
    echo "   Run: ./scripts/build_and_push.sh first"
    exit 1
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All validation checks passed!"
echo ""
echo "Safe to deploy:"
echo "  ./scripts/deploy_cloudformation.sh"

