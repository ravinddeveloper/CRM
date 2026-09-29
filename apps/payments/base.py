"""Base payment provider interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PaymentOrderResult:
    """Result from creating a payment order."""
    provider_order_id: str
    amount: Decimal
    currency: str
    client_secret: str | None = None  # Stripe
    key_id: str | None = None         # Razorpay
    extra: dict = field(default_factory=dict)


@dataclass
class RefundResult:
    """Result of a refund operation."""
    success: bool
    refund_id: str = ""
    amount_refunded: Decimal = Decimal("0.00")
    error: str = ""


class BasePaymentProvider(ABC):
    """Abstract payment provider interface."""

    @abstractmethod
    def create_order(
        self,
        amount: Decimal,
        currency: str,
        order_number: str,
        user_email: str,
        metadata: dict | None = None,
    ) -> PaymentOrderResult:
        """Initiate a payment order on the provider side."""
        ...

    @abstractmethod
    def verify_payment(
        self,
        provider_payment_id: str,
        provider_order_id: str,
        signature: str,
    ) -> bool:
        """Verify payment signature server-side. NEVER trust frontend."""
        ...

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        """Verify that an incoming webhook is genuinely from the provider."""
        ...

    @abstractmethod
    def get_payment_status(self, provider_payment_id: str) -> str:
        """Fetch the current status of a payment from the provider API."""
        ...

    @abstractmethod
    def process_refund(
        self,
        provider_payment_id: str,
        amount: Decimal,
        reason: str = "",
    ) -> RefundResult:
        """Issue a refund for a payment."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier for this provider."""
        ...
