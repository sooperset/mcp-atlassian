resource "aws_ecs_task_definition" "ai_coding_agent_td" {
  family = "${var.app_name}-tdf"
  requires_compatibilities = ["FARGATE"]
  network_mode = "awsvpc"
  cpu       = var.cpu_request
  memory    = var.mem_request
  execution_role_arn = aws_iam_role.tdf_execution_role.arn
  task_role_arn = aws_iam_role.tdf_task_role.arn
  
  container_definitions = jsonencode([
    {
      name      = "${var.app_name}-${var.target_environment}"
      image     = "${var.image_url}:${var.image_tag}"
      cpu       = var.cpu_request
      memory    = var.mem_request
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = data.aws_cloudwatch_log_group.log_group.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = var.target_environment
        }
      },
      environmentFiles = [
        {
          value: aws_s3_object.env_file.arn,
          type: "s3"
        }
      ],
    },
  ])
}