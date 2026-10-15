"""Thin wrappers over google-auth-oauthlib and MSAL so views stay testable
(tests replace these functions)."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class OAuthResult:
    subject: str
    email: str
    refresh_token: str
    scopes: list[str] = field(default_factory=list)


def _google_flow(request, scopes):
    from google_auth_oauthlib.flow import Flow

    config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(config, scopes=scopes)
    flow.redirect_uri = request.build_absolute_uri("/connectors/google/callback/")
    return flow


def google_authorization_url(request, scopes, state: str) -> str:
    flow = _google_flow(request, scopes)
    url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="false", state=state
    )
    # PKCE: the verifier must survive to the callback, which builds a new flow.
    request.session["google_pkce_verifier"] = flow.code_verifier
    return url


def google_exchange_code(request, scopes, code: str) -> OAuthResult:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    flow = _google_flow(request, scopes)
    verifier = request.session.pop("google_pkce_verifier", None)
    if not verifier:
        raise ValueError("The OAuth session has no PKCE verifier; start the link flow again.")
    flow.code_verifier = verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    claims = google_id_token.verify_oauth2_token(
        creds.id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
    )
    if not creds.refresh_token:
        raise ValueError("Google did not return a refresh token; the consent must be offline.")
    return OAuthResult(
        subject=claims["sub"],
        email=claims.get("email", ""),
        refresh_token=creds.refresh_token,
        scopes=list(creds.scopes or scopes),
    )


def _msal_app():
    import msal

    return msal.ConfidentialClientApplication(
        settings.MICROSOFT_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT}",
        client_credential=settings.MICROSOFT_CLIENT_SECRET,
    )


def microsoft_authorization_url(request, scopes, state: str) -> str:
    return _msal_app().get_authorization_request_url(
        scopes,
        state=state,
        redirect_uri=request.build_absolute_uri("/connectors/microsoft/callback/"),
    )


def microsoft_exchange_code(request, scopes, code: str) -> OAuthResult:
    result = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=scopes,
        redirect_uri=request.build_absolute_uri("/connectors/microsoft/callback/"),
    )
    if "refresh_token" not in result:
        raise ValueError(
            result.get("error_description", "Microsoft did not return a refresh token")
        )
    claims = result.get("id_token_claims") or {}
    return OAuthResult(
        subject=claims.get("oid") or claims.get("sub", ""),
        email=claims.get("preferred_username") or claims.get("email", ""),
        refresh_token=result["refresh_token"],
        scopes=result.get("scope", "").split(),
    )
