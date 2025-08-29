output "ecs_cluster_name" {
    value = data.aws_ecs_cluster.ecs.cluster_name
}

output "ecs_service_name" {
    value = aws_ecs_service.ai_coding_agent_service.name
}

output "target_group_arn" {
    value = aws_lb_target_group.app.arn
}

output "alb_dns_name" {
    value = aws_lb.app.dns_name
}

output "task_definition_arn" {
    value = aws_ecs_task_definition.ai_coding_agent_td.arn
}

output "fqdn" {
    value = aws_route53_record.app.fqdn
}
