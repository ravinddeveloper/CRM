"""Custom exception handler for DRF."""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Return consistent error responses for all API errors."""
    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Restructure the response
        error_data = {
            "success": False,
            "error": {
                "code": _get_error_code(exc),
                "message": _get_error_message(response.data),
                "details": response.data if isinstance(response.data, dict) else None,
            },
        }
        response.data = error_data
    else:
        # Unhandled exception — log it and return 500
        logger.exception("Unhandled exception in API view", exc_info=exc)
        response = Response(
            {
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _get_error_code(exc):
    """Map exception types to error codes."""
    from rest_framework.exceptions import (
        AuthenticationFailed,
        NotAuthenticated,
        NotFound,
        PermissionDenied,
        Throttled,
        ValidationError,
    )
    mapping = {
        AuthenticationFailed: "AUTHENTICATION_FAILED",
        NotAuthenticated: "NOT_AUTHENTICATED",
        PermissionDenied: "PERMISSION_DENIED",
        NotFound: "NOT_FOUND",
        ValidationError: "VALIDATION_ERROR",
        Throttled: "RATE_LIMIT_EXCEEDED",
    }
    return mapping.get(type(exc), "API_ERROR")


def _get_error_message(data):
    """Extract a readable message from DRF error data."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return data[0] if data else "An error occurred."
    if isinstance(data, dict):
        for key, val in data.items():
            if key != "detail":
                if isinstance(val, list):
                    return f"{key}: {val[0]}"
                return str(val)
        return str(data.get("detail", "An error occurred."))
    return "An error occurred."


class LMSException(Exception):
    """Base exception for all LMS business logic errors."""
    default_code = "LMS_ERROR"
    default_message = "An error occurred."

    def __init__(self, message=None, code=None):
        self.message = message or self.default_message
        self.code = code or self.default_code
        super().__init__(self.message)


class CourseAccessDenied(LMSException):
    default_code = "COURSE_ACCESS_DENIED"
    default_message = "You do not have access to this course."


class EnrollmentAlreadyExists(LMSException):
    default_code = "ENROLLMENT_EXISTS"
    default_message = "You are already enrolled in this course."


class PaymentVerificationFailed(LMSException):
    default_code = "PAYMENT_VERIFICATION_FAILED"
    default_message = "Payment verification failed."


class InvalidCoupon(LMSException):
    default_code = "INVALID_COUPON"
    default_message = "The coupon code is invalid or has expired."


class StorageError(LMSException):
    default_code = "STORAGE_ERROR"
    default_message = "A storage error occurred."
