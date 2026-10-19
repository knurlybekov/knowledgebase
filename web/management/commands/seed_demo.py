"""`manage.py seed_demo`: a demo organization with an admin, a steward and a
member, the synthetic corpus linked to the member and the steward through a
mocked connector, and one candidate decision record. Synthetic data only."""

from datetime import UTC, datetime

from django.core.management.base import BaseCommand

from accounts.api import User
from connectors.api import ConnectorLink, SyncScope, create_link, ensure_scope
from decisions.api import DecisionRecord, EvidenceInput, create_candidate
from infra.api import with_org
from knowledge.api import ChangeEvent, DownloadResult, SourceDocument, apply_change
from organizations.api import Membership, Organization, Principal
from retrieval.api import Chunk


class Command(BaseCommand):
    help = "Seed a demo organization with synthetic documents (no real data)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo-passphrase-change-me")

    def handle(self, *args, **options):
        from eval.corpus import documents

        org, _ = Organization.objects.get_or_create(
            slug="demo", defaults={"name": "Demo Organization"}
        )
        users = {}
        for role, email in (
            (Membership.ROLE_ADMIN, "admin@demo.invalid"),
            (Membership.ROLE_STEWARD, "steward@demo.invalid"),
            (Membership.ROLE_MEMBER, "member@demo.invalid"),
        ):
            user, created = User.objects.get_or_create(
                email=email, defaults={"display_name": role.title()}
            )
            if created:
                user.set_password(options["password"])
                user.save()
            with with_org(org.id, user.pk):
                Membership.objects.get_or_create(
                    organization=org, user=user, defaults={"role": role}
                )
            users[role] = user
        docs = documents()
        for user in (users[Membership.ROLE_MEMBER], users[Membership.ROLE_STEWARD]):
            link = create_link(
                org,
                user,
                provider=ConnectorLink.PROVIDER_GOOGLE,
                external_account_id=f"demo-{user.pk}",
                email=user.email,
                refresh_token="demo",
            )
            scope = ensure_scope(
                link, kind=SyncScope.KIND_GOOGLE_CHANGES, display_name="Demo Google Drive (mocked)"
            )
            # The mocked link has no real token: keep beat from polling it, or the
            # first scheduled sync marks the link as failed and hides the demo corpus.
            with with_org(org.id, user.pk):
                SyncScope.objects.filter(id=scope.id).update(enabled=False)
            for seq, (sid, body) in enumerate(docs.items(), start=1):
                sd = SourceDocument(
                    source_type="google_drive",
                    source_id=sid,
                    version_label="v1",
                    title=sid.split(":", 1)[1].replace("-", " ").title(),
                    mime_type="text/markdown",
                    source_url=f"https://docs.google.com/document/d/{sid.split(':', 1)[1]}",
                )
                apply_change(
                    link,
                    scope,
                    ChangeEvent(
                        kind="upsert",
                        source_id=sid,
                        seq=seq,
                        observed_at=datetime.now(UTC),
                        document=sd,
                    ),
                    lambda _sd, body=body: DownloadResult(
                        content=body, version_label="v1", mime_type="text/markdown"
                    ),
                )
        steward = Principal(
            user=users[Membership.ROLE_STEWARD], organization=org, role=Membership.ROLE_STEWARD
        )
        with with_org(org.id, steward.user_id):
            chunk = (
                Chunk.objects.filter(document__source_id="gdrive:hosting-decision")
                .order_by("position")
                .first()
            )
            exists = DecisionRecord.objects.filter(
                organization=org, title="Hosting provider selection (March 2025)"
            ).exists()
        if chunk and not exists:
            create_candidate(
                steward,
                title="Hosting provider selection (March 2025)",
                origin=DecisionRecord.ORIGIN_USER,
                evidence=[EvidenceInput(chunk_id=str(chunk.id), role="decision")],
            )
        self.stdout.write(
            "Demo ready: /o/demo/ — admin@demo.invalid, steward@demo.invalid, member@demo.invalid"
        )
