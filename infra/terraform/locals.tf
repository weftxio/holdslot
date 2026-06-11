locals {
  project = "holdslot"

  # Workspace-parameterised env: the default workspace is `dev`; a future production
  # rollout is `terraform workspace new prod` — no code change, just a new state slot.
  env = terraform.workspace == "default" ? "dev" : terraform.workspace

  name_prefix = "${local.project}-${local.env}"

  # Secrets are provisioned under holdslot/prod/* (already created + verified 2026-06-10).
  # Env-scoped prefix so a future prod workspace can read holdslot/prod/* while dev reads
  # the same shared external keys during build.
  secrets_prefix = "holdslot/prod"
}
