"""checkout: the CONFORMANT service.

Every attribute, metric, and event name comes from constants that Weaver generated
from registry/ (acme_semconv). A typo is a NameError at import time, not a silent
missing field in a dashboard three weeks later.
"""

from __future__ import annotations

import logging
import random
import secrets
import time

from flask import Flask, jsonify, request
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import SpanKind

from acme_semconv import attributes as attrs
from acme_semconv import metrics as acme_metrics
from telemetry import configure_telemetry

# OTLP has a schema_url field, but New Relic doesn't document keeping it, so the
# registry version also travels as a resource attribute for the Scorecard rule.
configure_telemetry(
    extra_resource_attributes={attrs.ACME_SCHEMA_URL: attrs.SCHEMA_URL},
    schema_url=attrs.SCHEMA_URL,
)

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)  # emits stable http.* when OTEL_SEMCONV_STABILITY_OPT_IN=http

tracer = trace.get_tracer("acme.checkout", schema_url=attrs.SCHEMA_URL)
meter = metrics.get_meter("acme.checkout", schema_url=attrs.SCHEMA_URL)
log = logging.getLogger("acme.checkout")

order_value = meter.create_histogram(
    acme_metrics.METRIC_ACME_ORDER_VALUE,
    unit=acme_metrics.METRIC_ACME_ORDER_VALUE_UNIT,
    description="Monetary value of placed orders.",
)

# The OpenTelemetry logging handler promotes this key to the LogRecord EventName.
OTEL_EVENT_NAME = "otel.event.name"
ORDER_PLACED_EVENT = "acme.order.placed"


@app.post("/orders")
def place_order():
    body = request.get_json(silent=True) or {}
    items = body.get("items") or [{"sku": "demo", "price": 10.0}]
    channel = body.get("channel", attrs.ACME_ORDER_CHANNEL_WEB)
    if channel not in attrs.ACME_ORDER_CHANNEL_VALUES:
        return jsonify(error=f"unknown channel {channel!r}"), 400
    payment = body.get("payment_method", attrs.ACME_PAYMENT_METHOD_CARD)
    if payment not in attrs.ACME_PAYMENT_METHOD_VALUES:
        return jsonify(error=f"unknown payment method {payment!r}"), 400

    order_id = f"ord_{secrets.token_hex(4)}"
    with tracer.start_as_current_span(
        "place order",
        kind=SpanKind.INTERNAL,
        attributes={
            attrs.ACME_ORDER_ID: order_id,
            attrs.ACME_ORDER_ITEM_COUNT: len(items),
            attrs.ACME_ORDER_CHANNEL: channel,
        },
    ):
        time.sleep(random.uniform(0.02, 0.12))  # pretend to price and persist
        total = round(sum(float(i.get("price", 0)) for i in items), 2)

    order_value.record(total, {attrs.ACME_ORDER_CHANNEL: channel, attrs.ACME_PAYMENT_METHOD: payment})
    log.info(
        "order placed",
        extra={
            OTEL_EVENT_NAME: ORDER_PLACED_EVENT,
            attrs.ACME_ORDER_ID: order_id,
            attrs.ACME_ORDER_CHANNEL: channel,
            attrs.ACME_PAYMENT_METHOD: payment,
        },
    )
    return jsonify(order_id=order_id, total=total), 201


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    # Flask's built-in server keeps the demo dependency-free; it is not for production.
    app.run(host="0.0.0.0", port=8080, threaded=True)
