# Lambda execution role — least privilege: write its own logs, call the Data API on this
# one cluster, read the cluster's master secret + the holdslot/prod/* app secrets, and
# send email via SES. No VPC permissions (Lambda is not in the VPC).

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-api-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# CloudWatch Logs — scoped to this function's log group.
resource "aws_iam_role_policy" "lambda_logs" {
  name = "logs"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
    }]
  })
}

# RDS Data API — only this cluster.
resource "aws_iam_role_policy" "lambda_data_api" {
  name = "rds-data-api"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "rds-data:BatchExecuteStatement",
        "rds-data:BeginTransaction",
        "rds-data:CommitTransaction",
        "rds-data:ExecuteStatement",
        "rds-data:RollbackTransaction",
      ]
      Resource = aws_rds_cluster.this.arn
    }]
  })
}

# Secrets Manager — the cluster master secret (for the Data API) + the app/external keys.
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "secrets"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_rds_cluster.this.master_user_secret[0].secret_arn,
        "arn:${data.aws_partition.current.partition}:secretsmanager:${var.region}:${var.aws_account_id}:secret:${local.secrets_prefix}/*",
      ]
    }]
  })
}

# SES — send transactional email from the verified domain only.
resource "aws_iam_role_policy" "lambda_ses" {
  name = "ses-send"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:SendEmail", "ses:SendRawEmail"]
      Resource = "*"
      Condition = {
        "StringEquals" = {
          "ses:FromAddress" = "no-reply@${var.ses_domain}"
        }
      }
    }]
  })
}
