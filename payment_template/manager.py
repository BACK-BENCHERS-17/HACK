"""Public payment manager exposed by the SDK."""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .config import AppConfig
from .database import MongoRepository
from .exceptions import OrderStateError, VerificationError
from .gmail import GmailService
from .models import Order, VerificationResult
from .purpose import generate_purpose
from .qr import build_upi_uri, generate_branded_qr
from .utils import generate_order_id, parse_amount, utcnow

# Regex patterns for extracting payment details from email text
_UTR_RE = re.compile(
    r"\b(?:UTR|RRN|UPI\s*Ref(?:erence)?(?:\s*No)?|Ref(?:\.?\s*No)?|Reference(?:\.?\s*No)?|Transaction\s*(?:Id|No)|Txn\s*(?:Id|No))[:\s\-/]+([A-Za-z0-9]{8,})",
    re.I,
)
_TXN_RE = re.compile(
    r"\b(?:Txn\s*(?:Id|No)?|Transaction\s*(?:Id|No)?|Reference(?:\.?\s*No)?|Ref(?:\.?\s*No)?)[:\s\-/]+([A-Za-z0-9]{8,})",
    re.I,
)
_SENDER_RE = re.compile(
    r"(?:received\s+(?:money\s+)?from|^from|\bfrom)[:\s]+"
    r"([A-Z0-9][A-Za-z0-9][A-Za-z0-9 .'\-]{1,60}?)"
    r"(?:"
    r"\s*(?:\bvia\b|\bon\b|\bby\b|\busing\b|\bfor\b|\bthrough\b|UPI|@)"
    r"|\s*[\u2022\u2013\u2014|<\.,!\u20b9]"
    r"|\s*[^\x00-\x7F]"
    r"|\s*\n"
    r"|\s*$"
    r")",
    re.I | re.M,
)

_STRIP_CHARS = ' .,\'"\\'


def _extract_payment_details(email_text: str) -> dict:
    """Extract UTR and sender name from email subject+body text."""
    utr_match = _UTR_RE.search(email_text)
    utr = (utr_match.group(1).strip() if utr_match else "").strip()
    txn_match = _TXN_RE.search(email_text)
    transaction_id = (txn_match.group(1).strip() if txn_match else "").strip()
    sender_match = _SENDER_RE.search(email_text)
    sender = ""
    if sender_match:
        sender = sender_match.group(1).strip()
        sender = re.sub(r"^(your|the)\s+", "", sender, flags=re.I).strip(_STRIP_CHARS)
    return {
        "utr": utr,
        "transaction_id": transaction_id or utr,
        "sender_name": sender or "Unknown",
    }


class PaymentManager:
    """A lightweight payment verification SDK for FamApp-style flows."""

    def __init__(
        self,
        *,
        default_upi_id: str | None = None,
        default_payee_name: str | None = None,
        config: AppConfig | None = None,
    ) -> None:
        self._config = config or AppConfig.from_env(
            default_upi_id=default_upi_id,
            default_payee_name=default_payee_name,
        )
        self._repository = MongoRepository(self._config)
        self._gmail = GmailService(self._config)

    def create(self, *, user_id: int, amount: float | int | str | Decimal) -> Order:
        """Create and persist a new pending payment order."""

        if not isinstance(user_id, int) or user_id <= 0:
            raise VerificationError("user_id must be a positive integer.")

        amount_decimal = parse_amount(amount)
        created_at = utcnow()
        expires_at = created_at + timedelta(minutes=self._config.order_expiry_minutes)
        order_id = generate_order_id()
        purpose = generate_purpose(self._config.purpose_prefix)
        upi_uri = build_upi_uri(
            upi_id=self._config.default_upi_id,
            payee_name=self._config.default_payee_name,
            amount=amount_decimal,
            purpose=purpose,
        )
        qr_image = generate_branded_qr(
            brand_name=self._config.brand_name,
            payee_name=self._config.default_payee_name,
            amount=amount_decimal,
            upi_uri=upi_uri,
            purpose=purpose,
            upi_id=self._config.default_upi_id,
        )

        order = Order(
            id=order_id,
            user_id=user_id,
            amount=amount_decimal,
            purpose=purpose,
            status="pending",
            qr_image=qr_image,
            upi_uri=upi_uri,
            payee_name=self._config.default_payee_name,
            created_at=created_at,
            expires_at=expires_at,
        )
        self._repository.save_order(order)
        return order

    def verify(self, order_id: str) -> dict[str, Any]:
        """Verify a pending order using IMAP and purpose matching."""

        order_id = str(order_id or "").strip()
        if not order_id:
            raise VerificationError("order_id is required.")

        order = self._repository.get_order(order_id)
        if order.status == "cancelled":
            raise OrderStateError("Cancelled orders cannot be verified.")
        if order.status == "verified":
            result = VerificationResult(
                order_id=order.id,
                verified=True,
                status="verified",
                message="Order is already verified.",
            ).to_dict()
            previous = self._repository.get_verification_log(order.id)
            if previous:
                result.update({
                    key: previous[key]
                    for key in (
                        "gmail_message_id", "purpose", "amount", "utr",
                        "transaction_id", "sender_name", "payment_time_ist",
                    )
                    if key in previous and previous[key] is not None
                })
            return result

        now = utcnow()
        if now >= order.expires_at:
            expired_order = self._repository.update_order_status(order.id, "expired")
            return VerificationResult(
                order_id=expired_order.id,
                verified=False,
                status="expired",
                message="Order has expired.",
            ).to_dict()

        message = self._gmail.find_matching_incoming_payment(
            lookback_hours=self._config.gmail_lookback_hours,
            order_created_at=order.created_at,
            expected_purpose=order.purpose,
            expected_amount=order.amount,
        )

        # If the UPI app stripped the purpose note, only accept the amount
        # fallback when no other live order could have produced that email.
        if (
            message is not None
            and message.purpose is None
            and not self._repository.amount_match_is_unambiguous(
                order, message.timestamp
            )
        ):
            message = None

        if message is None:
            return VerificationResult(
                order_id=order.id,
                verified=False,
                status="pending",
                message="No matching payment email was found.",
            ).to_dict()

        existing_log = self._repository.get_verification_log_by_message(message.message_id)
        if existing_log:
            if existing_log.get("order_id") == order.id:
                # The log may have been committed immediately before a worker
                # crashed while updating the order. Reconcile that safe state.
                updated_order = self._repository.update_order_status(order.id, "verified")
                result = VerificationResult(
                    order_id=updated_order.id,
                    verified=True,
                    status="verified",
                    message="Payment verified successfully.",
                    gmail_message_id=message.message_id,
                    purpose=updated_order.purpose,
                    amount=order.amount,
                    verified_at=utcnow(),
                ).to_dict()
                result.update({
                    key: existing_log[key]
                    for key in ("utr", "transaction_id", "sender_name", "payment_time_ist")
                    if existing_log.get(key) is not None
                })
                return result
            return VerificationResult(
                order_id=order.id,
                verified=False,
                status="pending",
                message="Matching email message was already processed.",
                gmail_message_id=message.message_id,
                purpose=message.purpose,
                amount=str(order.amount),
            ).to_dict()

        # Extract UTR and sender name from the email text
        combined_text = f"{message.subject}\n{message.body}"
        details = _extract_payment_details(combined_text)
        payment_time_ist = message.timestamp.astimezone(
            ZoneInfo("Asia/Kolkata")
        ).strftime("%d-%m-%Y %H:%M:%S")

        # Persist the details used by the bot before returning them.  This
        # makes a retry after a Telegram/network failure idempotent instead of
        # producing a second key with an empty transaction reference.
        utr = details["utr"] or f"FP-{message.message_id[:12]}"
        transaction_id = details["transaction_id"] or utr
        saved = self._repository.save_verification_log(
            order_id=order.id,
            gmail_message_id=message.message_id,
            purpose=order.purpose,
            gmail_message_timestamp=message.timestamp,
            amount=str(order.amount),
            utr=utr,
            transaction_id=transaction_id,
            sender_name=details["sender_name"],
            payment_time_ist=payment_time_ist,
        )
        if saved is False:
            # A competing order claimed this reference/message. Do not mark
            # this order verified or deliver anything from it.
            return VerificationResult(
                order_id=order.id,
                verified=False,
                status="pending",
                message="Matching payment reference was already processed.",
                gmail_message_id=message.message_id,
                purpose=message.purpose,
                amount=str(order.amount),
            ).to_dict()

        updated_order = self._repository.update_order_status(order.id, "verified")

        result = VerificationResult(
            order_id=updated_order.id,
            verified=True,
            status="verified",
            message="Payment verified successfully.",
            gmail_message_id=message.message_id,
            purpose=updated_order.purpose,
            amount=order.amount,
            verified_at=utcnow(),
        ).to_dict()

        # Enrich result with extracted payment details
        result["utr"] = utr
        result["transaction_id"] = transaction_id
        result["sender_name"] = details["sender_name"]
        result["payment_time_ist"] = payment_time_ist

        return result

    def status(self, order_id: str) -> str:
        """Return the current order status."""

        order = self._repository.get_order(order_id)
        if order.status == "pending" and utcnow() >= order.expires_at:
            self._repository.update_order_status(order.id, "expired")
            return "expired"
        return order.status

    def cancel(self, order_id: str) -> Order:
        """Cancel a pending order."""

        order = self._repository.get_order(order_id)
        if order.status != "pending":
            raise OrderStateError("Only pending orders can be cancelled.")
        return self._repository.update_order_status(order.id, "cancelled")
