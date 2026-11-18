"""OpenTelemetry bootstrap shared by both demo services.

Traces, metrics, and logs all go to OTLP. Endpoint, protocol, service name,
resource attributes, temporality, and export interval come from the standard
OTEL_* environment variables set in docker-compose.yaml.
"""

from __future__ import annotations

import logging
import os
import uuid

from opentelemetry import _logs, metrics, trace
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _exporters():
    """Pick OTLP exporters to match OTEL_EXPORTER_OTLP_PROTOCOL (default http/protobuf)."""
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    return OTLPSpanExporter(), OTLPMetricExporter(), OTLPLogExporter()


def configure_telemetry(
    extra_resource_attributes: dict[str, str] | None = None,
    schema_url: str | None = None,
) -> Resource:
    """Install global tracer, meter, and logger providers and bridge stdlib logging.

    `schema_url` is written to the OTLP Resource.schema_url field. Pass the same
    value in `extra_resource_attributes` (as acme.schema_url) if you need it to
    survive into a backend that doesn't keep the schema_url field.
    """
    attributes = {"service.instance.id": str(uuid.uuid4())}
    attributes.update(extra_resource_attributes or {})
    # Resource.create also reads OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES.
    resource = Resource.create(attributes, schema_url=schema_url)

    span_exporter, metric_exporter, log_exporter = _exporters()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    _logs.set_logger_provider(logger_provider)

    # Console output for humans, OTLP for machines. LoggingInstrumentor (from
    # opentelemetry-instrumentation-logging) replaces the SDK LoggingHandler,
    # which is deprecated since opentelemetry-sdk 1.40.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    LoggingInstrumentor().instrument()

    return resource
