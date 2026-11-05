"""One standard-library HTTPS request; no retries, redirects or credential files.

This transport keeps TLS certificate verification enabled. The caller supplies
the credential over stdin, never as an argument or a URL component.
"""
from __future__ import annotations

import http.client
import json
import re
import ssl
import sys

HOST = "openrouter.ai"
MAX_INPUT_BYTES = 13_000_000
MAX_RESPONSE_BYTES = 25_000_000


def redact(value, key):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k == "user_id" else redact(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        return value.replace(key, "[REDACTED]") if key else value
    return value


def perform(payload):
    key = payload.get("key", "")
    route = payload.get("route")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", key):
        raise ValueError("Invalid transport credential format")
    if route not in ("key", "chat/completions"):
        raise ValueError("Unsupported transport route")
    has_body = "body" in payload and payload["body"] is not None
    if (route == "key" and has_body) or (route == "chat/completions" and not has_body):
        raise ValueError("Route and method do not match")
    timeout_ms = payload.get("timeout_ms", 240000)
    if type(timeout_ms) not in (int, float) or not 1 <= timeout_ms <= 240000:
        raise ValueError("Timeout must be between1 and240000 milliseconds")
    body = json.dumps(payload["body"], separators=(",", ":"), ensure_ascii=False).encode() if has_body else None
    if body is not None and len(body) > 12_000_000:
        raise ValueError("Request size exceeds preflight limit")
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
               "X-Title": "Turing original GDPval evaluation v2", "X-OpenRouter-Metadata": "enabled"}
    if body is not None:
        headers["Content-Length"] = str(len(body))
    connection = None
    body_sent = False
    try:
        connection = http.client.HTTPSConnection(HOST, timeout=timeout_ms / 1000,
                                                context=ssl.create_default_context())
        # Conservative: any exception after invoking request leaves a possible
        # dispatch. This does not assert the server received all payload bytes.
        body_sent = has_body
        connection.request("POST" if has_body else "GET", "/api/v1/" + route, body=body, headers=headers)
        response = connection.getresponse()
        parts, size = [], 0
        while True:
            chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ValueError("response_size_limit")
            parts.append(chunk)
        text = b"".join(parts).decode("utf-8", errors="replace")
        try:
            decoded = json.loads(text)
        except ValueError:
            decoded = {"unparsed_response": text[:1000]}
        return redact({"status": response.status, "headers": {"retry-after": response.getheader("retry-after")},
                       "body": decoded, "request_body_sent": body_sent}, key)
    except Exception as error:
        message = str(error).replace(key, "[REDACTED]")[:300]
        return {"status": None, "request_body_sent": body_sent, "transport_error": message}
    finally:
        if connection is not None:
            connection.close()


def main():
    key = ""
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("Transport input exceeds size limit")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Transport input must be an object")
        key = payload.get("key", "")
        if not isinstance(key, str):
            key = ""
        result = perform(payload)
    except Exception as error:
        # Validation fails before any connection; do not echo raw input/errors.
        message = str(error).replace(key, "[REDACTED]") if key else str(error)
        result = {"status": None, "request_body_sent": False, "transport_error": message[:300]}
    sys.stdout.write(json.dumps(redact(result, key), ensure_ascii=False))


if __name__ == "__main__":
    main()
