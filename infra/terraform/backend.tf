# Remote state in S3 with native lockfile (no DynamoDB). The bucket is created once by
# scripts/bootstrap-state.sh before the first `terraform init` (state can't store its own
# backend — the classic chicken-and-egg). State is keyed per workspace, so the `dev`
# workspace and a future `prod` workspace never collide.
terraform {
  backend "s3" {
    bucket       = "holdslot-tfstate-138743894336"
    key          = "holdslot/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
