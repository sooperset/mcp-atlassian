resource "aws_security_group" "ecs_service_sg" {
  name        = "${var.app_name}-ecs-sg-${var.target_environment}"
  description = "ECS tasks behind ALB"
  vpc_id      = data.aws_vpc.default_vpc.id

  ingress {
    description     = "From ALB only"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

resource "aws_ecs_service" "ai_coding_agent_service" {
  name            = "${var.app_name}-service-${var.target_environment}"
  cluster         = data.aws_ecs_cluster.ecs.arn
  task_definition = aws_ecs_task_definition.ai_coding_agent_td.arn
  launch_type     = "FARGATE"
  desired_count   = var.desired_replica_count
  enable_execute_command = var.enable_execute_command 

  network_configuration {
    subnets         = data.aws_subnets.default_subnets.ids
    security_groups = [aws_security_group.ecs_service_sg.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "${var.app_name}-${var.target_environment}"
    container_port   = var.container_port
  }

  health_check_grace_period_seconds = 60

  depends_on = [aws_lb_listener.https]
}
