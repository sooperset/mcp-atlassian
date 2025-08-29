data "aws_vpc" "default_vpc" {
    default = true
}

data "aws_subnets" "default_subnets" {
    filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default_vpc.id]
    }
}

data "aws_ecs_cluster" "ecs" {
  cluster_name = var.ecs_name
}

data "aws_cloudwatch_log_group" "log_group" {
  name = var.log_group_name
}