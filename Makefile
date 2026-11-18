# Requires: weaver v0.28.0 on PATH (https://github.com/open-telemetry/weaver/releases),
# Docker, and Terraform 1.3+ for the scorecard.

WEAVER   ?= weaver
REGISTRY := registry
BASELINE ?= https://github.com/your-org/telemetry-registry.git@main[registry]
GENERATED := services/checkout/acme_semconv

.PHONY: check diff generate check-generated up down logs findings scorecard-plan scorecard-apply

## Standardize left -----------------------------------------------------------

check:            ## Lint the registry + run Acme's Rego house rules
	$(WEAVER) registry check -r $(REGISTRY) -p policies/registry

diff:             ## Show changes vs a baseline registry (BASELINE=<vdir>)
	$(WEAVER) registry diff -r $(REGISTRY) --baseline-registry "$(BASELINE)"

generate:         ## Regenerate Python constants for the checkout service
	$(WEAVER) registry generate -r $(REGISTRY) -p policies/registry --templates templates python $(GENERATED)

check-generated: generate   ## Fail if generated code is stale
	@git diff --exit-code -- $(GENERATED) || (echo "Generated code is stale: run 'make generate' and commit." && exit 1)

## Verify right ---------------------------------------------------------------

up:               ## Start services, Collector, and Weaver live-check
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f collector weaver

findings:         ## Tail Weaver findings as they leave the Collector
	docker compose logs -f collector | grep --line-buffered -i "weaver.live_check.finding\|LogRecord"

# Loads .env, maps NEW_RELIC_USER_API_KEY to the provider's NEW_RELIC_API_KEY.
TF_ENV = set -a; [ -f .env ] && . ./.env; set +a; \
	export NEW_RELIC_API_KEY="$${NEW_RELIC_USER_API_KEY:-$$NEW_RELIC_API_KEY}" \
	TF_VAR_account_id="$$NEW_RELIC_ACCOUNT_ID" TF_VAR_region="$${NEW_RELIC_REGION:-us}"; \
	[ -z "$$CHECKOUT_SERVICE_NAME" ] || export TF_VAR_checkout_service_name="$$CHECKOUT_SERVICE_NAME"; \
	[ -z "$$LEGACY_CART_SERVICE_NAME" ] || export TF_VAR_legacy_cart_service_name="$$LEGACY_CART_SERVICE_NAME"

scorecard-plan:   ## Show what Terraform would change in the scorecard
	$(TF_ENV); cd scorecard/terraform && terraform init -input=false && terraform plan

scorecard-apply:  ## Create or update the scorecard (needs NEW_RELIC_USER_API_KEY, NEW_RELIC_ACCOUNT_ID)
	$(TF_ENV); cd scorecard/terraform && terraform init -input=false && terraform apply
