variable "account_id" {
  description = "New Relic account the rules run against."
  type        = number
}

variable "region" {
  description = "New Relic region: us or eu."
  type        = string
  default     = "us"

  validation {
    condition     = contains(["us", "eu"], lower(var.region))
    error_message = "region must be us or eu."
  }
}

variable "checkout_service_name" {
  description = "service.name of the checkout entity (matches CHECKOUT_SERVICE_NAME in .env)."
  type        = string
  default     = "weaver-checkout"
}

variable "legacy_cart_service_name" {
  description = "service.name of the legacy-cart entity (matches LEGACY_CART_SERVICE_NAME in .env)."
  type        = string
  default     = "weaver-legacy-cart"
}
