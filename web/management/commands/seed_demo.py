"""`manage.py seed_demo`: a demo organization with an admin, a steward and a
member, a synthetic corpus linked to every demo user through a mocked connector,
and one candidate decision record. Synthetic data only.

`--corpus org` (default) seeds the organizational corpus into /o/demo/;
`--corpus academic` seeds lecture notes, a slide deck and a report into /o/studies/."""

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
        parser.add_argument("--corpus", choices=("org", "academic"), default="org")

    def handle(self, *args, **options):
        from eval.corpus import documents

        academic = options["corpus"] == "academic"
        slug, name = ("studies", "My studies") if academic else ("demo", "Demo Organization")
        org, _ = Organization.objects.get_or_create(slug=slug, defaults={"name": name})
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
        if academic:
            from eval.corpus_academic import documents as academic_documents

            docs = academic_documents()
        else:
            docs = {sid: (body, "text/markdown", None) for sid, body in documents().items()}
        for user in users.values():
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
            for seq, (sid, (body, mime, title)) in enumerate(docs.items(), start=1):
                sd = SourceDocument(
                    source_type="google_drive",
                    source_id=sid,
                    version_label="v1",
                    title=title or sid.split(":", 1)[1].replace("-", " ").title(),
                    mime_type=mime,
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
                    lambda _sd, body=body, mime=mime: DownloadResult(
                        content=body, version_label="v1", mime_type=mime
                    ),
                )
        steward = Principal(
            user=users[Membership.ROLE_STEWARD], organization=org, role=Membership.ROLE_STEWARD
        )
        if academic:
            source_id = "gdrive:software-engineering-capstone-decision-2026-03"
            title = "Capstone backend framework: Django (March 2026)"
        else:
            source_id = "gdrive:hosting-decision"
            title = "Hosting provider selection (March 2025)"
        with with_org(org.id, steward.user_id):
            chunks = Chunk.objects.filter(document__source_id=source_id).order_by("position")
            # Prefer the passage under the "Decision" heading; fall back to the first chunk.
            chunk = next(
                (c for c in chunks if c.heading_path and c.heading_path[-1] == "Decision"), None
            )
            chunk = chunk or chunks.first()
            exists = DecisionRecord.objects.filter(organization=org, title=title).exists()
        if chunk and not exists:
            create_candidate(
                steward,
                title=title,
                origin=DecisionRecord.ORIGIN_USER,
                evidence=[EvidenceInput(chunk_id=str(chunk.id), role="decision")],
            )
        self.stdout.write(f"Demo ready: /o/{slug}/ (admin@, steward@ and member@demo.invalid)")
