from django.db import migrations

from infra.sql import composite_fk_sql, org_unique_sql, rls_policy_reverse_sql, rls_policy_sql

TABLES = ["retrieval_chunk", "retrieval_embedding", "retrieval_retrievallog"]
CONSTRAINTS = [
    org_unique_sql("retrieval_chunk"),
    "ALTER TABLE retrieval_chunk ADD CONSTRAINT chunk_version_id_uniq UNIQUE (version_id, id);",
    composite_fk_sql("retrieval_chunk", "organization_id, document_id", "knowledge_document", "organization_id, id", "chunk_document_org_fk"),
    composite_fk_sql("retrieval_chunk", "document_id, version_id", "knowledge_documentversion", "document_id, id", "chunk_version_document_fk"),
    composite_fk_sql("retrieval_embedding", "organization_id, chunk_id", "retrieval_chunk", "organization_id, id", "embedding_chunk_org_fk"),
]


class Migration(migrations.Migration):
    dependencies = [("retrieval", "0001_initial"), ("knowledge", "0002_rls")]

    operations = [
        migrations.RunSQL(sql="".join(rls_policy_sql(t) for t in TABLES), reverse_sql="".join(rls_policy_reverse_sql(t) for t in TABLES)),
        migrations.RunSQL(sql="\n".join(CONSTRAINTS), reverse_sql=migrations.RunSQL.noop),
    ]
