resource "aws_iam_role" "tdf_execution_role" {
  name = "ecsTaskExecutionRole-${var.app_name}-${var.target_environment}"

  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
  })

  tags = {
    CreatedBy = "Phil",
    CreatedFor = "MCP Atlassian",
    ManagedBy = "terraform"
  }
}


resource "aws_iam_role_policy" "execution_role_policy" {
  name = "ecsTaskExecutionRole-${var.app_name}-${var.target_environment}"
  role = aws_iam_role.tdf_execution_role.id

  policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Action   = ["ecr:GetAuthorizationToken"]
          Effect   = "Allow"
          Resource = "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage"
            ],
            "Resource": var.registry_arn
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "${data.aws_cloudwatch_log_group.log_group.arn}*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:GetObjectVersion"
            ],
            "Resource": "${var.s3_arn}*"
        }
      ]
    })
}

resource "aws_iam_role" "tdf_task_role" {
  name = "ecsTaskRole-${var.app_name}-${var.target_environment}"

  assume_role_policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
  })

  tags = {
    CreatedBy = "Phil",
    CreatedFor = "AI Coding Agent",
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role_policy" "task_role_policy" {
  name = "ecsTaskRole-${var.app_name}-${var.target_environment}"
  role = aws_iam_role.tdf_task_role.id

  policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Action   = [
            "ssmmessages:CreateControlChannel",
            "ssmmessages:CreateDataChannel",
            "ssmmessages:OpenControlChannel",
            "ssmmessages:OpenDataChannel",
            "ecs:ExecuteCommand"
          ]
          Effect   = "Allow"
          Resource = "*"
        },
      ]
    })
}


