# SES — verified sending domain for transactional email (password reset now; approval /
# booking / feedback / reminders later). DKIM tokens are emitted as outputs to add to DNS;
# the identity isn't usable until those CNAMEs resolve (and the account leaves the sandbox
# for non-verified recipients — an operational step, not Terraform).

resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.ses_domain
}
