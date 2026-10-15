"""Login, logout and password reset. Login attempts are rate limited per
client address through the shared limiter in web.ratelimit."""

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.http import HttpResponse

from web.api import rate_limited


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if rate_limited(request, "login", settings.RATE_LIMIT_LOGIN_PER_15MIN, 900):
            return HttpResponse("Too many login attempts. Try again later.", status=429)
        return super().post(request, *args, **kwargs)


class LogoutView(auth_views.LogoutView):
    pass


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    success_url = "/accounts/password-reset/done/"


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = "/accounts/login/"
