# "Semantic Convention Conformance" scorecard, managed with the New Relic provider.
#
# Source of truth stays in ../scorecard.yaml (levels, rules, weights) and
# ../nrql/*.nrql (queries). `terraform apply` creates the scorecard and updates it
# in place when those files change.
#
# Auth: NEW_RELIC_API_KEY (a User key with Scorecards modify permission).
# `make scorecard-apply` maps NEW_RELIC_USER_API_KEY from .env to it.

terraform {
  required_version = ">= 1.3"
  required_providers {
    newrelic = {
      source  = "newrelic/newrelic"
      version = ">= 3.101"
    }
  }
}

provider "newrelic" {
  account_id = var.account_id
  region     = upper(var.region)
}

locals {
  spec = yamldecode(file("${path.module}/../scorecard.yaml"))

  # Only the two entities in this demo are graded.
  services = "'${var.checkout_service_name}', '${var.legacy_cart_service_name}'"

  # Drop `--` comment lines, collapse whitespace, fill in the service list.
  queries = {
    for r in local.spec.rules : r.name => replace(join(" ", [
      for line in split("\n", file("${path.module}/../${r.nrql_file}")) :
      trimspace(replace(replace(line, "/--.*$/", ""), "/\\s+/", " "))
      if trimspace(replace(line, "/--.*$/", "")) != ""
    ]), "{{SERVICES}}", local.services)
  }
}

resource "newrelic_scorecard_rule" "this" {
  for_each = { for r in local.spec.rules : r.name => r }

  name           = each.value.name
  description    = try(each.value.description, "")
  enabled        = true
  progress_level = each.value.level
  impact_weight  = each.value.weight
  run_interval   = each.value.run_interval

  nrql_engine {
    accounts = [var.account_id]
    query    = local.queries[each.key]
  }
}

resource "newrelic_scorecard" "this" {
  name        = local.spec.name
  description = trimspace(local.spec.description)
  rule_ids    = [for r in newrelic_scorecard_rule.this : r.id]

  dynamic "progress_levels" {
    for_each = local.spec.progress_levels
    content {
      id             = progress_levels.value.id
      name           = progress_levels.value.name
      description    = try(progress_levels.value.description, "")
      hex_color_code = try(progress_levels.value.color, "#11845C")
    }
  }
}

output "scorecard_id" {
  value = newrelic_scorecard.this.id
}

output "queries" {
  description = "Final NRQL sent for each rule."
  value       = local.queries
}
