def _serialize_interrupt(interrupt_obj) -> dict:
    """Serialize a HITLRequest interrupt value into a JSON-safe dict."""
    value = getattr(interrupt_obj, "value", interrupt_obj)
    if not isinstance(value, dict):
        value = getattr(value, "__dict__", {})

    action_requests = []
    for ar in value.get("action_requests", []):
        if not isinstance(ar, dict):
            ar = getattr(ar, "__dict__", {})
        action_requests.append(
            {
                "action": ar.get("name", ""),
                "args": ar.get("args", {}),
                "description": ar.get("description", ""),
            }
        )

    review_configs = []
    for rc in value.get("review_configs", []):
        if not isinstance(rc, dict):
            rc = getattr(rc, "__dict__", {})
        review_configs.append(
            {
                "actionName": rc.get("action_name", ""),
                "allowedDecisions": list(rc.get("allowed_decisions", [])),
            }
        )

    return {
        "actionRequests": action_requests,
        "reviewConfigs": review_configs,
    }
