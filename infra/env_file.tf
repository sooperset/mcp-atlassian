data "aws_s3_bucket" "app_bucket" {
    bucket = var.s3_bucket_name
}

resource "aws_s3_object" "env_file" {
    bucket = data.aws_s3_bucket.app_bucket.id
    key    = "mcp-atlassian/env_files/${var.target_environment}/.env"
    source = ".env"
    etag   = filemd5(".env")
    content_type = "text/plain"
}