# House rules evaluated by `weaver registry check -p policies/registry`.
#
# Runs against the RESOLVED registry (schema v1: input.groups[_].attributes[_]).
# Findings use Weaver's finding structure: id, level, message, context.
#
# Rules only judge groups Acme owns. Imported upstream groups (for example the
# http.server.request.duration metric) are OpenTelemetry's responsibility.
package after_resolution

import rego.v1

# Groups that DEFINE Acme-owned attributes.
attribute_group_prefix := "registry.acme."

# Substrings that must never appear in an Acme attribute name.
pii_markers := {"email", "phone", "ssn", "card_number", "password", "dob"}

acme_owned(group) if contains(group.id, ".acme.")

# 1. Attributes defined in registry.acme.* groups must live in the acme.* namespace.
deny contains finding if {
	group := input.groups[_]
	startswith(group.id, attribute_group_prefix)
	attr := group.attributes[_]
	not startswith(attr.name, "acme.")
	finding := {
		"id": "acme_namespace_required",
		"level": "violation",
		"context": {"attribute_name": attr.name, "group_id": group.id},
		"message": sprintf("Attribute '%s' in group '%s' must use the 'acme.' namespace. Reference upstream attributes from an acme.refs.* group instead of redefining them.", [attr.name, group.id]),
	}
}

# 2. Every Acme attribute needs a human-readable brief.
deny contains finding if {
	group := input.groups[_]
	startswith(group.id, attribute_group_prefix)
	attr := group.attributes[_]
	trim_space(object.get(attr, "brief", "")) == ""
	finding := {
		"id": "acme_brief_required",
		"level": "violation",
		"context": {"attribute_name": attr.name, "group_id": group.id},
		"message": sprintf("Attribute '%s' must have a non-empty brief.", [attr.name]),
	}
}

# 3. Attribute names must not suggest personal data.
deny contains finding if {
	group := input.groups[_]
	attr := group.attributes[_]
	startswith(attr.name, "acme.")
	some marker in pii_markers
	contains(attr.name, marker)
	finding := {
		"id": "acme_pii_attribute_name",
		"level": "violation",
		"context": {"attribute_name": attr.name, "marker": marker},
		"message": sprintf("Attribute '%s' looks like personal data ('%s'). PII must not be emitted as telemetry.", [attr.name, marker]),
	}
}

# 4. Acme's stable signals may only reference stable attributes.
deny contains finding if {
	group := input.groups[_]
	acme_owned(group)
	group.type in {"span", "metric", "event"}
	object.get(group, "stability", "development") == "stable"
	attr := group.attributes[_]
	object.get(attr, "stability", "development") != "stable"
	finding := {
		"id": "acme_unstable_attribute_in_stable_signal",
		"level": "violation",
		"signal_type": group.type,
		"signal_name": group.id,
		"context": {"attribute_name": attr.name, "group_id": group.id, "stability": object.get(attr, "stability", "development")},
		"message": sprintf("Stable signal '%s' references '%s', which is not stable. Promote the attribute or lower the signal's stability.", [group.id, attr.name]),
	}
}

# 5. Acme metrics should declare a unit (suggestion, not a blocker).
deny contains finding if {
	group := input.groups[_]
	acme_owned(group)
	group.type == "metric"
	object.get(group, "unit", "") == ""
	finding := {
		"id": "acme_metric_unit_missing",
		"level": "improvement",
		"signal_type": "metric",
		"signal_name": object.get(group, "metric_name", group.id),
		"context": {"group_id": group.id},
		"message": sprintf("Metric '%s' should declare a unit.", [object.get(group, "metric_name", group.id)]),
	}
}
