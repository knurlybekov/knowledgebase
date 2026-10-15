"""Build a provider client for a link from its encrypted refresh token."""

from .crypto import decrypt_token
from .models import ConnectorLink
from .providers.google import GoogleApiClient, GoogleDriveClient
from .providers.graph import GraphClient, GraphHttpApi


def client_for(link: ConnectorLink):
    refresh = decrypt_token(link.refresh_token_encrypted)
    if link.provider == ConnectorLink.PROVIDER_GOOGLE:
        return GoogleDriveClient(GoogleApiClient(refresh))
    return GraphClient(GraphHttpApi(refresh))
