"""Thin API views for authentication. Logic is delegated to services."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.api.serializers import (
    ChangePasswordSerializer,
    EmailTokenObtainPairSerializer,
    ForgotPasswordSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserSerializer,
)
from apps.accounts.services import auth as auth_service
from apps.common.responses import success_response


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses=UserSerializer)
    def post(self, request: Request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = auth_service.register_user(**serializer.validated_data)
        return success_response(
            data=UserSerializer(user).data,
            message="Account created successfully.",
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """Obtain access & refresh tokens (plus the user profile)."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"
    serializer_class = EmailTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request={"application/json": {"type": "object", "properties": {"refresh": {"type": "string"}}}})
    def post(self, request: Request):
        refresh = request.data.get("refresh")
        if not refresh:
            return success_response(message="Logged out.")
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            # Token already invalid/expired — logout is idempotent.
            pass
        return success_response(message="Logged out.")


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request: Request):
        return success_response(data=UserSerializer(request.user).data)

    @extend_schema(request=ProfileUpdateSerializer, responses=UserSerializer)
    def patch(self, request: Request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = auth_service.update_profile(user=request.user, **serializer.validated_data)
        return success_response(data=UserSerializer(user).data, message="Profile updated.")


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer)
    def post(self, request: Request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service.change_password(user=request.user, **serializer.validated_data)
        return success_response(message="Password changed successfully.")


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(request=ForgotPasswordSerializer)
    def post(self, request: Request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service.request_password_reset(**serializer.validated_data)
        # Always the same response, whether or not the email exists.
        return success_response(
            message="If an account exists for that email, a reset link has been sent."
        )


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    @extend_schema(request=ResetPasswordSerializer)
    def post(self, request: Request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service.reset_password(
            raw_token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password"],
        )
        return success_response(message="Password has been reset. You can now log in.")
