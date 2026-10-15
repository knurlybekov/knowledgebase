"""Request id and actor propagation."""

import uuid

from .context import actor_id_var, request_id_var


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id
        token_req = request_id_var.set(request_id)
        token_actor = None
        try:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                token_actor = actor_id_var.set(str(user.pk))
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token_req)
            if token_actor is not None:
                actor_id_var.reset(token_actor)
