variable "aws_region" {
    description = "AWS region for deployment"
    type        = string
}

variable "s3_arn" {
    description = "ARN of S3 bucket"
    type        = string
}

variable env_file_arn {
    description = "Image tag used"
    type        = string
}

variable cpu_request {
    description = "Amount of vCPU requested"
    type        = number
    default = 1024
}

variable mem_request {
    description = "Amount of Mem requested"
    type        = number
    default = 2048
}

variable app_name {
    description = "Name of App"
    type        = string
}
variable desired_replica_count {
    description = "Image tag used"
    type        = number
    default = 1
}

variable target_environment {
    description = "Environemt of application"
    type        = string
}

variable log_group_name {
    description = "Name of log group"
    type        = string
}

variable container_port {
    description = "Port for application"
    type        = number
}

variable hosted_zone_id {
    type        = string
}

variable domain_name {
    type        = string
}

variable enable_execute_command {
    type = bool
    default = false
}

variable ecs_name {
    type        = string
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN of the issued ACM certificate in the same region as the ALB"
}

variable "auth_token" {
  type        = string
  description = "Authorization token for accessing the service"
  sensitive   = true
}

variable "s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket"
}

variable image_url {
    description = "URL to the image"
    type        = string
}

variable image_tag {
    description = "Image tag used"
    type        = string
}

variable "registry_arn" {
    description = "ARN of ECR"
    type        = string
}
