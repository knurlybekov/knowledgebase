"""`manage.py run_eval`: ingest the synthetic corpus into a throwaway evaluation
organization, run the golden queries, write eval/results/<date>.md."""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.api import User
from connectors.api import ConnectorLink, SyncScope, create_link, ensure_scope
from infra.api import with_org
from knowledge.api import ChangeEvent, DownloadResult, SourceDocument, apply_change
from organizations.api import Membership, Organization, Principal


class Command(BaseCommand):
    help = "Run the retrieval and grounding evaluation on the synthetic corpus."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="eval-synthetic")

    def handle(self, *args, **options):
        from datetime import UTC, datetime

        from eval.corpus import documents
        from eval.runner import run_all

        slug = slugify(options["org"])
        org, _ = Organization.objects.get_or_create(
            slug=slug, defaults={"name": "Evaluation (synthetic)"}
        )
        user, _ = User.objects.get_or_create(
            email=f"eval@{slug}.invalid", defaults={"display_name": "Evaluation user"}
        )
        with with_org(org.id, user.pk):
            Membership.objects.get_or_create(
                organization=org, user=user, defaults={"role": Membership.ROLE_MEMBER}
            )
        link = create_link(
            org,
            user,
            provider=ConnectorLink.PROVIDER_GOOGLE,
            external_account_id="eval",
            email=user.email,
            refresh_token="none",
        )
        scope = ensure_scope(link, kind=SyncScope.KIND_GOOGLE_CHANGES)
        for seq, (sid, body) in enumerate(documents().items(), start=1):
            sd = SourceDocument(
                source_type="google_drive",
                source_id=sid,
                version_label="v1",
                title=sid.split(":", 1)[1],
                mime_type="text/markdown",
                source_url=f"https://docs.google.com/document/d/{sid.split(':', 1)[1]}",
            )
            event = ChangeEvent(
                kind="upsert",
                source_id=sid,
                seq=seq + 1000,
                observed_at=datetime.now(UTC),
                document=sd,
            )
            apply_change(
                link,
                scope,
                event,
                lambda _sd, body=body: DownloadResult(
                    content=body, version_label="v1", mime_type="text/markdown"
                ),
            )
        principal = Principal(user=user, organization=org, role="member")
        rows, path = run_all(principal)
        self.stdout.write(f"wrote {path}")
        for r in rows:
            self.stdout.write(
                f"{r.id}: recall@5={r.recall5} mrr={r.mrr} state={r.evidence_state} claims={r.claims} supported={r.supported}"
            )
