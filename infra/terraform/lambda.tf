# API Lambda. Terraform owns the function + config; CI (A5) ships the real code via
# `aws lambda update-function-code` + publish + alias-shift, so the code attributes are
# under ignore_changes — Terraform and the deploy pipeline don't fight over the artifact.
#
# A placeholder package (returns 200 for any route) is baked so the function exists and the
# API is reachable immediately after A2, before the real FastAPI bundle lands in A5.

data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/.build/placeholder.zip"

  source {
    filename = "app/main.py"
    content  = <<-PY
      def handler(event, context):
          return {
              "statusCode": 200,
              "headers": {"content-type": "application/json"},
              "body": "{\"status\": \"ok\", \"placeholder\": true}",
          }
    PY
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = "${local.name_prefix}-api"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "app.main.handler"
  memory_size   = 512
  # 300s gives the async workers headroom: structuring (DeepSeek V4 Pro thinking + web search,
  # ~55-76s) AND a full fit-scoring wave (up to `_SCORE_WORKERS` concurrent reasoning calls at ~70s
  # each, one wave per `ASYNC_BATCH_MAX`) must finish before the worker is hard-killed — a mid-batch
  # kill leaves a zombie `running` job (see scoring.MAX_JOB_AGE_SECONDS, kept above this). Synchronous
  # API requests are unaffected — API Gateway still caps those at its own 30s; this only governs the
  # off-gateway background invocation.
  timeout = 300

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  # Publish a version on each Terraform-managed change; SnapStart snapshots versions.
  publish = true

  snap_start {
    apply_on = "PublishedVersions"
  }

  environment {
    variables = {
      HOLDSLOT_ENV            = local.env
      HOLDSLOT_DB_CLUSTER_ARN = aws_rds_cluster.this.arn
      HOLDSLOT_DB_SECRET_ARN  = aws_rds_cluster.this.master_user_secret[0].secret_arn
      HOLDSLOT_DB_NAME        = aws_rds_cluster.this.database_name
      HOLDSLOT_SECRETS_PREFIX = local.secrets_prefix
      HOLDSLOT_CORS_ORIGINS   = join(",", var.web_origins)
      HOLDSLOT_WEB_BASE_URL   = var.web_base_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  lifecycle {
    # CI owns the code artifact post-bootstrap.
    ignore_changes = [filename, source_code_hash]
  }
}

# Async-invocation policy for the background structuring worker (self async-invoke hits the
# unqualified function = $LATEST). Zero retries: the worker records its own failures as a job
# `error`, so an AWS-level retry would only risk re-spending a (billed) LLM call. Events older
# than ~2 min are dropped rather than queued behind a slow run.
resource "aws_lambda_function_event_invoke_config" "api_async" {
  function_name                = aws_lambda_function.api.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 120
}

# Stable invoke target. API Gateway points at this alias; CI shifts it to each new
# published version. SnapStart-restored versions are served through the alias.
resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.api.function_name
  function_version = aws_lambda_function.api.version

  lifecycle {
    ignore_changes = [function_version]
  }
}
