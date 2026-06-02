TAG_ALIASES = {
    "roles": "Roles",
    "gamification": "Gamification",
    "user_profile": "User Profile",
    "userprofile": "User Profile",
    "waitlist": "Waitlist",
    "banking": "Banking",
    "treasury": "Treasury",
    "support": "Support",
    "web": "Web",
    "partners": "Partner Services",
    "partner services": "Partner Services",
    "fmcg": "FMCG",
    "accounts": "Accounts",
    "self_service": "Self Service",
    "selfservice": "Self Service",
    "vas": "VAS",
    "adverts": "Brand Ads",
    "brand ads": "Brand Ads",
    "webhooks": "Webhooks",
    "kyc": "KYC",
    "wallet": "Wallet",
}


def normalize_tags(result, generator, **kwargs):
    """Merge auto-generated lowercase tags with their manually named equivalents."""

    def canonical(tag):
        return TAG_ALIASES.get(tag.lower().replace("-", "_"), tag)

    # Remap every operation's tags
    for path_data in result.get("paths", {}).values():
        for operation in path_data.values():
            if isinstance(operation, dict) and "tags" in operation:
                operation["tags"] = [canonical(t) for t in operation["tags"]]

    # Rebuild the top-level tags list with only unique canonical names
    seen = {}
    for tag in result.get("tags", []):
        name = canonical(tag["name"])
        if name not in seen:
            seen[name] = {**tag, "name": name}

    result["tags"] = list(seen.values())
    return result
