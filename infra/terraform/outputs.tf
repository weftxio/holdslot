output "api_base_url" {
  description = "Public base URL of the HTTP API (set as apps/web API_BASE_URL in A5)."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "aurora_cluster_arn" {
  description = "Aurora cluster ARN — Data API target (app env HOLDSLOT_DB_CLUSTER_ARN)."
  value       = aws_rds_cluster.this.arn
}

output "aurora_master_secret_arn" {
  description = "ARN of the RDS-managed master secret (Data API auth + connection test)."
  value       = aws_rds_cluster.this.master_user_secret[0].secret_arn
}

output "aurora_database_name" {
  description = "Initial database name."
  value       = aws_rds_cluster.this.database_name
}

output "lambda_function_name" {
  description = "API Lambda name — CI updates code here (A5)."
  value       = aws_lambda_function.api.function_name
}

output "lambda_alias" {
  description = "Live alias the API Gateway invokes."
  value       = aws_lambda_alias.live.name
}

output "ses_dkim_tokens" {
  description = "Add these as CNAME records (token._domainkey.<domain>) to verify SES DKIM."
  value       = aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens
}
