from connectors.api import ConnectorLink, SyncScope, create_link, ensure_scope


def make_link(org, user, provider: str = ConnectorLink.PROVIDER_GOOGLE) -> ConnectorLink:
    return create_link(
        org,
        user,
        provider=provider,
        external_account_id=f"acct-{user.pk}",
        email=user.email,
        refresh_token="refresh-token-test",
        oauth_scopes=["drive.readonly"],
    )


def make_scope(link: ConnectorLink) -> SyncScope:
    kind = (
        SyncScope.KIND_GOOGLE_CHANGES
        if link.provider == ConnectorLink.PROVIDER_GOOGLE
        else SyncScope.KIND_GRAPH_DRIVE
    )
    return ensure_scope(
        link, kind=kind, external_id="" if kind == SyncScope.KIND_GOOGLE_CHANGES else "drive-1"
    )
