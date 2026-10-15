"""Celery base class for organization-scoped work (D5).

`OrgAwareTask` carries `org_id` as the first argument, sets the ContextVar for
logging, and runs `run(org_id, ...)`. It opens NO transaction: the task body
wraps each database write in `with_org(org_id)` and keeps external calls
(connector HTTP, embeddings, runner streaming) outside transactions.
"""

from celery import Task

from .context import org_id_var
from .rls import ensure_rls_enforcing_role


class OrgAwareTask(Task):
    abstract = True
    typing = False

    def __call__(self, *args, **kwargs):
        org_id = kwargs.pop("org_id", None)
        if org_id is None and args:
            org_id = args[0]
            args = args[1:]
        if org_id is None:
            raise TypeError(f"{type(self).__name__} requires org_id (positional or kwarg)")
        ensure_rls_enforcing_role()
        token = org_id_var.set(str(org_id))
        try:
            return self.run(org_id, *args, **kwargs)
        finally:
            org_id_var.reset(token)
