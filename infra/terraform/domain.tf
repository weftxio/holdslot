# Custom domain for the API: api.tryholdslot.com.
# DNS for tryholdslot.com is in Route53 but managed outside this stack, so the cert
# validation CNAME and the final alias record are added by hand (see outputs). Two phases:
#   Phase 1 (enable_api_domain_mapping = false): create the ACM cert. Add the
#           `acm_validation_records` CNAME in Route53; wait for the cert to show ISSUED.
#   Phase 2 (enable_api_domain_mapping = true): create the API Gateway custom domain +
#           mapping, then add `api.tryholdslot.com CNAME -> api_custom_domain_target`.

variable "api_domain_name" {
  description = "Custom domain for the HTTP API."
  type        = string
  default     = "api.tryholdslot.com"
}

variable "enable_api_domain_mapping" {
  description = "Flip to true only after the ACM cert is ISSUED (phase 2). Enabled 2026-06-11."
  type        = bool
  default     = true
}

resource "aws_acm_certificate" "api" {
  domain_name       = var.api_domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_domain_name" "api" {
  count       = var.enable_api_domain_mapping ? 1 : 0
  domain_name = var.api_domain_name

  domain_name_configuration {
    certificate_arn = aws_acm_certificate.api.arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "api" {
  count       = var.enable_api_domain_mapping ? 1 : 0
  api_id      = aws_apigatewayv2_api.this.id
  domain_name = aws_apigatewayv2_domain_name.api[0].id
  stage       = aws_apigatewayv2_stage.default.id
}

output "acm_validation_records" {
  description = "Add these CNAME record(s) in Route53 to validate the API cert (phase 1)."
  value = [
    for o in aws_acm_certificate.api.domain_validation_options : {
      name  = o.resource_record_name
      type  = o.resource_record_type
      value = o.resource_record_value
    }
  ]
}

output "api_custom_domain_target" {
  description = "Phase 2: add api.tryholdslot.com CNAME -> this value."
  value       = try(aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name, null)
}
