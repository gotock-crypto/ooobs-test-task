import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify

app = Flask(__name__)

SOURCE_URL = "https://test.ooobs.ru/api/orders"
REQUEST_TIMEOUT = 15


def normalize_phone(value):
    """Return a Russian phone number as +7XXXXXXXXXX, or None if invalid."""
    if not isinstance(value, str):
        return None

    digits = "".join(ch for ch in value if ch.isdigit())

    if len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]

    if len(digits) != 11 or digits[0] != "7":
        return None

    return "+" + digits


def as_amount(value):
    """Convert amounts to comparable numbers; invalid amounts sort below valid ones."""
    if isinstance(value, bool):
        return float("-inf")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float("-inf")


def as_timestamp(value):
    """Parse ISO timestamps, treating timestamps without a timezone as UTC."""
    if not isinstance(value, str) or not value:
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return float("-inf")


def extract_orders(payload):
    """Accept the API's common list and wrapped-list response shapes."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("orders", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Source API response does not contain an orders list")


@app.get("/")
def health():
    return jsonify({"status": "ok", "endpoint": "/result"})


@app.get("/result")
def synchronize():
    try:
        response = requests.get(SOURCE_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        orders = extract_orders(response.json())
    except (requests.RequestException, ValueError) as exc:
        app.logger.exception("Unable to fetch or parse source orders")
        return jsonify({"error": "source_api_unavailable", "detail": str(exc)}), 502

    received = len(orders)
    selected = {}
    invalid_dropped = 0
    duplicates_merged = 0

    for order in orders:
        if not isinstance(order, dict):
            invalid_dropped += 1
            continue

        phone = normalize_phone(order.get("phone"))
        if phone is None:
            invalid_dropped += 1
            continue

        candidate = {
            "name": order.get("name", ""),
            "phone": phone,
            "email": order.get("email", ""),
            "amount": order.get("amount", 0),
        }
        created_at = order.get("created_at")
        previous = selected.get(phone)

        if previous is None:
            selected[phone] = (candidate, created_at)
            continue

        duplicates_merged += 1
        old_client, old_created_at = previous
        candidate_amount = as_amount(candidate["amount"])
        old_amount = as_amount(old_client["amount"])

        if (
            candidate_amount > old_amount
            or (
                candidate_amount == old_amount
                and as_timestamp(created_at) > as_timestamp(old_created_at)
            )
        ):
            selected[phone] = (candidate, created_at)

    clients = [entry[0] for entry in selected.values()]
    return jsonify({
        "clients": clients,
        "stats": {
            "received": received,
            "unique": len(clients),
            "duplicates_merged": duplicates_merged,
            "invalid_dropped": invalid_dropped,
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
