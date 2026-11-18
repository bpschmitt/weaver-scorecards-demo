"""legacy-cart: the DRIFTING service.

It is instrumented with OpenTelemetry and produces perfectly reasonable-looking
telemetry. It just never adopted the registry, which is exactly how most estates
look. Every problem below is deliberate and realistic:

  1. Hand-typed attribute names (order_id, itemCount) instead of registry names.
  2. A non-conformant metric name (cartTotal).
  3. Pre-stable HTTP attributes (http.method, http.target, http.status_code),
     because the service never set OTEL_SEMCONV_STABILITY_OPT_IN=http.
  4. An email address in a log attribute (PII).
  5. No service.version, no acme.team, and the deprecated deployment.environment
     (set in docker-compose.yaml), so it can't be owned or versioned.
  6. No registry schema URL, so nothing marks it as built against the contract.

Weaver never sees this service at build time, so its CI is green. Weaver
live-check (fed from the Collector) and the Scorecard in New Relic both catch it.
"""

from __future__ import annotations

import logging
import random
import time
import uuid

from flask import Flask, jsonify, request
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from telemetry import configure_telemetry

configure_telemetry()  # no schema URL, no registry attributes

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

tracer = trace.get_tracer("cart")
meter = metrics.get_meter("cart")
log = logging.getLogger("cart")

cart_total = meter.create_histogram("cartTotal", unit="USD")


@app.post("/cart/checkout")
def checkout():
    body = request.get_json(silent=True) or {}
    items = body.get("items") or [{"sku": "demo", "price": 10.0}]
    email = body.get("email", f"shopper{random.randint(1, 999)}@example.com")

    order_id = str(uuid.uuid4())
    with tracer.start_as_current_span("checkout") as span:
        span.set_attribute("order_id", order_id)
        span.set_attribute("itemCount", len(items))
        time.sleep(random.uniform(0.05, 0.25))
        total = round(sum(float(i.get("price", 0)) for i in items), 2)

    cart_total.record(total, {"channel": "web"})
    log.info("checkout complete", extra={"order_id": order_id, "customer_email": email})
    return jsonify(order_id=order_id, total=total), 201


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, threaded=True)
