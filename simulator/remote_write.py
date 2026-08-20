"""Minimal Prometheus remote-write encoder (protobuf wire format, hand-rolled —
WriteRequest/TimeSeries/Label/Sample only) + snappy compression via cramjam.
Used to push the studio telemetry to Grafana Cloud's hosted Prometheus.
"""
from __future__ import annotations

import struct

import cramjam
import httpx


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _len_delim(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(payload)) + payload


def _string(field: int, s: str) -> bytes:
    return _len_delim(field, s.encode("utf-8"))


def _label(name: str, value: str) -> bytes:
    return _string(1, name) + _string(2, value)


def _sample(value: float, ts_ms: int) -> bytes:
    return _tag(1, 1) + struct.pack("<d", value) + _tag(2, 0) + _varint(ts_ms)


def _timeseries(metric: str, labels: dict[str, str], value: float, ts_ms: int) -> bytes:
    body = _len_delim(1, _label("__name__", metric))
    for k, v in sorted(labels.items()):
        body += _len_delim(1, _label(k, v))
    body += _len_delim(2, _sample(value, ts_ms))
    return body


def push_series(url: str, user: str, token: str,
                series: list[tuple[str, dict[str, str], float]],
                ts_ms: int, timeout: float = 8.0) -> int:
    """Push samples that carry their own label sets (per-title slate series)."""
    payload = b"".join(
        _len_delim(1, _timeseries(name, labels, value, ts_ms)) for name, labels, value in series
    )
    compressed = bytes(cramjam.snappy.compress_raw(payload))
    resp = httpx.post(
        url,
        content=compressed,
        auth=(user, token),
        headers={
            "content-type": "application/x-protobuf",
            "content-encoding": "snappy",
            "x-prometheus-remote-write-version": "0.1.0",
            "user-agent": "genesis-simulator/0.1",
        },
        timeout=timeout,
    )
    return resp.status_code


def push(url: str, user: str, token: str, metrics: dict[str, float],
         labels: dict[str, str], ts_ms: int, timeout: float = 8.0) -> int:
    """Push a batch of gauge samples; returns HTTP status code."""
    payload = b"".join(
        _len_delim(1, _timeseries(name, labels, value, ts_ms)) for name, value in metrics.items()
    )
    compressed = bytes(cramjam.snappy.compress_raw(payload))
    resp = httpx.post(
        url,
        content=compressed,
        auth=(user, token),
        headers={
            "content-type": "application/x-protobuf",
            "content-encoding": "snappy",
            "x-prometheus-remote-write-version": "0.1.0",
            "user-agent": "genesis-simulator/0.1",
        },
        timeout=timeout,
    )
    return resp.status_code
