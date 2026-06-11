# Aurora Serverless v2 (PostgreSQL) + RDS Data API.
# The DB lives in a VPC (it must), but the Data API is an HTTPS endpoint reached through
# the AWS API — so Lambda calls it WITHOUT joining the VPC (no NAT, SnapStart-safe). We
# use the account's default VPC subnets: simplest now, and the Data API path means no
# inbound network rules are needed from Lambda.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name_prefix}-aurora"
  subnet_ids = data.aws_subnets.default.ids
}

# No custom security group: Data API access goes through the AWS API, not the VPC network
# path, so nothing needs to reach the DB port and the VPC's default SG suffices. (Omitting
# vpc_security_group_ids lets RDS attach the default SG — one fewer resource, no EC2 perms.)
resource "aws_rds_cluster" "this" {
  cluster_identifier = "${local.name_prefix}-aurora"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  # 16.6+ supports scale-to-zero (0 ACU auto-pause).
  engine_version = "16.6"

  database_name = "holdslot"

  # RDS-managed master secret — no password ever in Terraform state or source. The secret
  # ARN is exposed as an output; the app reads it via secretsmanager:GetSecretValue.
  master_username             = "holdslot_admin"
  manage_master_user_password = true

  # The Data API (HTTP endpoint) — the whole reason Lambda stays out of the VPC.
  enable_http_endpoint = true

  db_subnet_group_name    = aws_db_subnet_group.this.name
  storage_encrypted       = true
  backup_retention_period = 7

  serverlessv2_scaling_configuration {
    min_capacity             = var.aurora_min_acu
    max_capacity             = var.aurora_max_acu
    seconds_until_auto_pause = var.aurora_min_acu == 0 ? var.aurora_seconds_until_auto_pause : null
  }

  # Dev convenience — revisit for the prod workspace (final snapshot + deletion protection).
  skip_final_snapshot = true
}

resource "aws_rds_cluster_instance" "this" {
  identifier         = "${local.name_prefix}-aurora-1"
  cluster_identifier = aws_rds_cluster.this.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
}
