# Custom live-check advisor: evaluated against every attribute Weaver receives
# over OTLP (`weaver registry live-check --advice-policies policies/live_check`).
#
# Registry checks can only judge NAMES. This catches PII in VALUES, which only
# shows up at runtime — e.g. an email address stuffed into a free-form attribute.
#
# Supplying --advice-policies replaces Weaver's default OpenTelemetry advice, so
# otel_default.rego (vendored from Weaver) sits in the same directory to keep it.
# Built-in advisors (missing_attribute, deprecated, type_mismatch, ...) always run.
package live_check_advice

import rego.v1

email_pattern := `^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$`

deny contains finding if {
	attr := input.sample.attribute
	is_string(attr.value)
	regex.match(email_pattern, attr.value)
	finding := {
		"id": "acme_pii_value",
		"level": "violation",
		"context": {"attribute_key": attr.name},
		"message": sprintf("Attribute '%s' carries a value that looks like an email address. PII must not be emitted as telemetry.", [attr.name]),
	}
}
