from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def org_url(context, name, *args, **kwargs):
    """`reverse()` plus the `/o/<slug>` prefix the middleware stripped."""
    path = reverse(name, args=args, kwargs=kwargs)
    prefix = context.get("org_prefix") or ""
    return f"{prefix}{path}"


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None
