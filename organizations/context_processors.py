def organization(request):
    return {
        "organization": getattr(request, "organization", None),
        "membership": getattr(request, "membership", None),
        "org_prefix": getattr(request, "org_prefix", ""),
    }
