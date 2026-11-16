"""Create and verify Razorpay UPI QR-code payments."""

from datetime import datetime, timedelta, timezone
import time

import razorpay
import requests


class PaymentAuthenticationError(Exception):
    pass


class PaymentConfigurationError(Exception):
    pass


class PaymentProviderError(Exception):
    pass


class _StatusTrackingSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.last_status_code = None

    def request(self, method, url, **kwargs):
        response = super().request(method, url, **kwargs)
        self.last_status_code = response.status_code
        return response


def _client(key_id, key_secret):
    if not key_id or not key_secret:
        raise PaymentConfigurationError
    return razorpay.Client(
        auth=(key_id, key_secret),
        session=_StatusTrackingSession(),
    )


def _call_api(client, session, operation):
    try:
        return operation()
    except Exception as exc:
        if session.last_status_code in (401, 403):
            raise PaymentAuthenticationError from exc
        raise PaymentProviderError from exc


def validate_credentials(key_id, key_secret):
    client = _client(key_id, key_secret)
    response = _call_api(
        client,
        client.session,
        lambda: client.qrcode.all({"count": 1}),
    )
    if not isinstance(response, dict):
        raise PaymentProviderError
    return True


def create_qr_code(amount, key_id, key_secret, name, description):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 100:
        raise ValueError("Amount must be an integer of at least 100 paise.")

    client = _client(key_id, key_secret)
    close_by = int(time.time()) + 16 * 60
    qr_code = _call_api(
        client,
        client.session,
        lambda: client.qrcode.create({
            "type": "upi_qr",
            "name": name[:40],
            "usage": "single_use",
            "fixed_amount": True,
            "payment_amount": amount,
            "description": description[:255],
            "close_by": close_by,
        }),
    )
    if not isinstance(qr_code, dict) or not qr_code.get("id"):
        raise PaymentProviderError

    image_url = qr_code.get("image_url")
    if not isinstance(image_url, str) or not image_url.startswith("https://"):
        raise PaymentProviderError
    try:
        response = requests.get(image_url, timeout=(3, 10))
        response.raise_for_status()
        image = response.content
        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            raise PaymentProviderError
        if not image or len(image) > 2_000_000:
            raise PaymentProviderError
    except PaymentProviderError:
        raise
    except Exception as exc:
        raise PaymentProviderError from exc

    return {
        "id": qr_code["id"],
        "image": image,
        "close_by": close_by,
    }


def close_qr_code(qr_code_id, key_id, key_secret):
    client = _client(key_id, key_secret)
    return _call_api(
        client,
        client.session,
        lambda: client.qrcode.close(qr_code_id),
    )


def verify_qr_payment(qr_code_id, expected_amount, key_id, key_secret):
    client = _client(key_id, key_secret)
    response = _call_api(
        client,
        client.session,
        lambda: client.qrcode.fetch_all_payments(qr_code_id, {"count": 100}),
    )
    payments = response.get("items") if isinstance(response, dict) else None
    if not isinstance(payments, list):
        raise PaymentProviderError

    for payment in payments:
        if (
            not isinstance(payment, dict)
            or payment.get("status") != "captured"
            or payment.get("amount") != expected_amount
            or payment.get("currency") != "INR"
            or payment.get("qr_code_id") not in (None, qr_code_id)
        ):
            continue
        payment_id = payment.get("id")
        if not payment_id:
            continue
        acquirer_data = payment.get("acquirer_data")
        acquirer_data = acquirer_data if isinstance(acquirer_data, dict) else {}
        reference = acquirer_data.get("rrn") or acquirer_data.get("upi_transaction_id") or payment_id
        created_at = payment.get("created_at")
        if isinstance(created_at, int):
            payment_time = datetime.fromtimestamp(
                created_at, timezone.utc
            ).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime(
                "%d %b %Y, %I:%M %p IST"
            )
        else:
            payment_time = ""
        return {
            "verified": True,
            "status": "verified",
            "utr": str(reference),
            "transaction_id": str(payment_id),
            "sender_name": "Razorpay UPI",
            "payment_time_ist": payment_time,
        }

    return {
        "verified": False,
        "status": "pending",
        "message": "Razorpay has not captured a matching payment yet.",
    }
