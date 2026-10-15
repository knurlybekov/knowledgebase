"""Authorization paths executed through Django as the runtime role kb_app, and
the relational consistency constraints."""

import pytest
from django.db import IntegrityError, connection

from infra.api import with_org
from knowledge.api import Document, DocumentVersion, visible_documents
from knowledge.tests.helpers import ingest_markdown, principal_for
from organizations.tests.factories import make_membership, make_org, make_user
from retrieval.api import Chunk


@pytest.mark.django_db(transaction=True)
def test_cross_org_and_cross_user_visibility_as_runtime_role(runtime_role):
    with connection.cursor() as cur:
        cur.execute("SELECT current_user")
        assert cur.fetchone()[0] == "kb_app"
    org1, org2 = make_org(), make_org()
    a, b = make_user(), make_user()
    make_membership(org1, a)
    make_membership(org2, b)
    ingest_markdown(org1, a, {"gdrive:one": b"# One\nalpha"})
    ingest_markdown(org2, b, {"gdrive:two": b"# Two\nbeta"})
    with with_org(org1.id):
        assert list(
            visible_documents(principal_for(org1, a)).values_list("source_id", flat=True)
        ) == ["gdrive:one"]
        assert (
            visible_documents(principal_for(org2, b)).count() == 0
        )  # explicit predicate denies, RLS too
        assert Document.objects.filter(organization=org2).count() == 0
    with with_org(org2.id):
        assert list(
            visible_documents(principal_for(org2, b)).values_list("source_id", flat=True)
        ) == ["gdrive:two"]
    # Nothing without a scope.
    assert Document.objects.count() == 0
    # The runtime role cannot read the audit log at all.
    from django.db.utils import ProgrammingError

    with pytest.raises(ProgrammingError):
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM infra_auditlog")


@pytest.mark.django_db(transaction=True)
def test_relational_consistency_constraints_reject_mismatches():
    org1, org2 = make_org(), make_org()
    a, b = make_user(), make_user()
    make_membership(org1, a)
    make_membership(org2, b)
    ingest_markdown(org1, a, {"gdrive:one": b"# One\nalpha"})
    ingest_markdown(org2, b, {"gdrive:two": b"# Two\nbeta"})
    with with_org(org1.id):
        doc1 = Document.objects.get(source_id="gdrive:one")
    with with_org(org2.id):
        doc2 = Document.objects.get(source_id="gdrive:two")
        v2 = doc2.versions.get()
    # A chunk in org2 pointing at org1's document: the organization FK pair rejects it.
    with pytest.raises(IntegrityError), with_org(org2.id):
        Chunk.objects.create(
            organization=org2, document=doc1, version=v2, position=99, text="x", content_hash="h"
        )
    # Same organization, but a version that belongs to another document.
    with with_org(org2.id):
        other = Document.objects.create(
            organization=org2, source_type="google_drive", source_id="gdrive:other"
        )
        other_version = DocumentVersion.objects.create(
            organization=org2, document=other, version_label="v1"
        )
    with pytest.raises(IntegrityError), with_org(org2.id):
        Chunk.objects.create(
            organization=org2,
            document=doc2,
            version=other_version,
            position=98,
            text="x",
            content_hash="h",
        )
