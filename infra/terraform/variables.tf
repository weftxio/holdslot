variable "region" {
  description = "AWS region (locked to us-east-1 in Phase A)."
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "HoldSlot AWS account — guards against applying to the wrong account."
  type        = string
  default     = "138743894336"
}

variable "aurora_min_acu" {
  description = "Aurora Serverless v2 minimum capacity. 0 = scale-to-zero (auto-pause) for launch cost."
  type        = number
  default     = 0
}

variable "aurora_max_acu" {
  description = "Aurora Serverless v2 maximum capacity (ACU)."
  type        = number
  default     = 4
}

variable "aurora_seconds_until_auto_pause" {
  description = "Idle seconds before Aurora pauses to 0 ACU (only used when aurora_min_acu = 0)."
  type        = number
  default     = 3600
}

variable "ses_domain" {
  description = "Sending domain for transactional email (verified in SES; DKIM records output for DNS)."
  type        = string
  default     = "tryholdslot.com"
}

variable "budget_limit_usd" {
  description = "Monthly AWS cost budget; alerts fire at 80% (forecast) and 100% (actual)."
  type        = number
  default     = 100
}

variable "budget_alert_emails" {
  description = "Recipients for AWS budget alerts (the two founders)."
  type        = list(string)
  default     = ["jason.tse@tryholdslot.com", "jason.wong@tryholdslot.com"]
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention for the API Lambda."
  type        = number
  default     = 30
}

variable "web_base_url" {
  description = "Base URL of the web app this API serves — used to build links in emails (e.g. password reset). Dev points at the Amplify dev branch."
  type        = string
  default     = "https://dev.d2w95n49ooprjf.amplifyapp.com"
}

variable "web_origins" {
  description = "Browser origins allowed to call the API (CORS). The HoldSlot web app is served from the Amplify custom domain + branch URLs; localhost is for dev."
  type        = list(string)
  default = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://tryholdslot.com",
    "https://www.tryholdslot.com",
    "https://main.d2w95n49ooprjf.amplifyapp.com",
    "https://dev.d2w95n49ooprjf.amplifyapp.com",
  ]
}
