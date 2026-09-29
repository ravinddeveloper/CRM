"""Accounts REST API views."""
from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    LoginSerializer,
    PasswordChangeSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import AccountService

User = get_user_model()


@api_view(["POST"])
@permission_classes([AllowAny])
def register_api_view(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        from apps.notifications.tasks import send_verification_email
        user = AccountService.register_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            first_name=serializer.validated_data["first_name"],
            last_name=serializer.validated_data["last_name"],
        )
        send_verification_email.delay(str(user.id))
        return Response({
            "success": True,
            "message": "Account created. Please verify your email.",
            "user": UserSerializer(user).data,
        }, status=status.HTTP_201_CREATED)
    return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_api_view(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = authenticate(
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response({
                "success": False,
                "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}
            }, status=status.HTTP_401_UNAUTHORIZED)
        if user.is_suspended:
            return Response({
                "success": False,
                "error": {"code": "ACCOUNT_SUSPENDED", "message": "Account suspended."}
            }, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        return Response({
            "success": True,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        })
    return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_api_view(request):
    try:
        refresh_token = request.data.get("refresh")
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
    except Exception:
        pass
    return Response({"success": True, "message": "Logged out."})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def profile_api_view(request):
    user = request.user
    if request.method == "GET":
        return Response({"success": True, "data": UserSerializer(user).data})
    serializer = UserSerializer(user, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"success": True, "data": serializer.data})
    return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password_api_view(request):
    serializer = PasswordChangeSerializer(data=request.data)
    if serializer.is_valid():
        from django.core.exceptions import ValidationError
        try:
            AccountService.change_password(
                user=request.user,
                old_password=serializer.validated_data["old_password"],
                new_password=serializer.validated_data["new_password"],
            )
            return Response({"success": True, "message": "Password changed."})
        except ValidationError as e:
            return Response({"success": False, "error": {"message": str(e)}}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_email_api_view(request):
    token = request.data.get("token")
    if not token:
        return Response({"success": False, "error": {"message": "Token required."}}, status=400)
    from django.core.exceptions import ValidationError
    try:
        AccountService.verify_email(token)
        return Response({"success": True, "message": "Email verified."})
    except ValidationError as e:
        return Response({"success": False, "error": {"message": str(e)}}, status=400)


@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password_api_view(request):
    email = request.data.get("email", "")
    ip = request.META.get("REMOTE_ADDR")
    token = AccountService.create_password_reset_token(email, ip_address=ip)
    if token:
        from apps.notifications.tasks import send_password_reset_email
        send_password_reset_email.delay(str(token.id))
    return Response({"success": True, "message": "If the email exists, a reset link has been sent."})


@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password_api_view(request):
    token = request.data.get("token")
    new_password = request.data.get("password")
    if not token or not new_password:
        return Response({"success": False, "error": {"message": "Token and password required."}}, status=400)
    from django.core.exceptions import ValidationError
    try:
        AccountService.reset_password(token, new_password)
        return Response({"success": True, "message": "Password reset successfully."})
    except ValidationError as e:
        return Response({"success": False, "error": {"message": str(e)}}, status=400)
