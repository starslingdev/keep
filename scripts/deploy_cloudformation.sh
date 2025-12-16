#!/bin/bash
#
# Deploy Continuum infrastructure to AWS using CloudFormation
#

set -e

STACK_NAME=${STACK_NAME:-continuum-prod}
AWS_REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-prod}

echo "🚀 Deploying Continuum to AWS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Stack: $STACK_NAME"
echo "Region: $AWS_REGION"
echo "Environment: $ENVIRONMENT"
echo ""

# Generate secure password if not provided
if [ -z "$DB_PASSWORD" ]; then
  export DB_PASSWORD="Keep$(openssl rand -base64 12 | tr -d '/+=')!"
  echo "Generated database password: $DB_PASSWORD"
  echo "(Save this - you'll need it for direct DB access)"
  echo ""
fi

echo "☁️  Deploying CloudFormation stack..."
echo "(This will take ~10-15 minutes...)"
echo ""

aws cloudformation deploy \
  --template-file aws-cloudformation.yaml \
  --stack-name $STACK_NAME \
  --parameter-overrides \
      Environment=$ENVIRONMENT \
      DatabasePassword=$DB_PASSWORD \
      GitHubAppId="" \
      SentryAuthToken="" \
  --capabilities CAPABILITY_IAM \
  --region $AWS_REGION

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Get outputs
echo "📋 Stack Outputs:"
aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $AWS_REGION \
  --query 'Stacks[0].Outputs' \
  --output table

echo ""
echo "🎉 Your Continuum instance is live!"
echo ""
echo "Next steps:"
echo "  1. Visit the SignupURL above"
echo "  2. Create your first account"
echo "  3. Start analyzing incidents!"

