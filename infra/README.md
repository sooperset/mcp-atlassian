# Jira-mcp-auth-bridge Infrastructure
The Jira-mcp-auth-bridge is managed by Terraform, deployed to AWS and uses the AWS ECS service.

## Deployments to new organization / accounts

**1. Create a new tfvars file**:
```bash
cp infra/var_files/example.tfvars infra/var_files/<environment-name>.tfvars
```

**2. Create the following services**:
1. ECR
2. S3
3. ECS Cluster
    - Create a namespace, recommendation: default
    - Using AWS Fargate
4. Log Group
    - Use the ECS cluster name

**3. Update the tfvars**
**4. Update the providers.tf file with the target bucket**
**5. Upload the .env file to the S3 bucket, update the tfvars with the file arn**



## SSHing into containers

All the values can be found in the ECS console for the specific deployment. At the moment, only staging deployments are open to SSH access.

```bash
aws ecs execute-command \
  --cluster <cluster name> \
  --task <task id> \
  --container <container name> \
  --command "/bin/bash" \
  --interactive
```

## Local management and testing

```bash
terraform init -backend-config="key=mcp-atlassian/terraform/staging.tfstate"

terraform apply \
  -var-file=var_files/ai.tfvars.safe \
  -var "domain_name=mcp-atlassian-staging" \
  -var "target_environment=staging" \
  -var "enable_execute_command=true" \
  -var "auth_token=<token>"
```