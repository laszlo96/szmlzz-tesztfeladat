output "opensearch_endpoint" {
  value = "https://${aws_opensearch_domain.main.endpoint}"
}

output "opensearch_dashboard_endpoint" {
  value = "https://${aws_opensearch_domain.main.dashboard_endpoint}"
}

output "opensearch_domain_arn" {
  value = aws_opensearch_domain.main.arn
}

output "otel_collector_role_arn" {
  value = aws_iam_role.otel_collector.arn
}

output "mcp_server_role_arn" {
  value = aws_iam_role.mcp_server.arn
}

output "alerts_sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
