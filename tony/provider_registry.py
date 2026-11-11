"""Managed OAuth registry: one place that knows how every core app signs a user in.

Composio-style managed auth works because the platform owns one OAuth app per
provider: the user clicks Connect, lands on Google/Slack/GitHub's own consent
screen, and comes back connected. Nothing is pasted.

This module is that registry. It supplies the authorize/token endpoints, the
least-privilege scopes, the identity endpoint used to show "connected as
you@company.com", and the revocation endpoint used when an account is removed.
It overrides whatever the public catalog says, because catalogs routinely ship
an empty or stale auth block, and a dead Connect button is worse than none.

Credential resolution order for every provider:
  1. platform env vars (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, ...)
  2. the OAuthProvider table, filled once by the owner in Tony's provider console
  3. dynamic client registration, for providers that support it (RFC 7591)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .catalog import ActionSpec, AppSpec, AuthSpec


@dataclass(frozen=True)
class Provider:
    slug: str
    name: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    env: tuple[str, str]
    identity_url: str = ""
    identity_method: str = "GET"
    identity_json: tuple[str, ...] = ()
    revoke_url: str = ""
    revoke_mode: str = "params"        # params | json | bearer | basic
    pkce: bool = False
    authorize_params: dict[str, str] = field(default_factory=dict)
    token_params: dict[str, str] = field(default_factory=dict)
    docs: str = ""
    category: str = "Productivity"
    base_url: str = ""


GOOGLE = dict(
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    identity_url="https://openidconnect.googleapis.com/v1/userinfo",
    identity_json=("email", "name"),
    revoke_url="https://oauth2.googleapis.com/revoke",
    env=("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    pkce=True,
    authorize_params={"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"},
    docs="https://console.cloud.google.com/apis/credentials",
)

PROVIDERS: dict[str, Provider] = {
    "gmail": Provider(
        slug="gmail", name="Gmail", category="Communication",
        base_url="https://gmail.googleapis.com",
        scopes=("openid", "email", "profile",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/gmail.send"),
        **GOOGLE),
    "google_drive": Provider(
        slug="google_drive", name="Google Drive", category="Storage",
        base_url="https://www.googleapis.com/drive/v3",
        scopes=("openid", "email", "profile",
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive.readonly"),
        **GOOGLE),
    "google_calendar": Provider(
        slug="google_calendar", name="Google Calendar", category="Calendar",
        base_url="https://www.googleapis.com/calendar/v3",
        scopes=("openid", "email", "profile",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.readonly"),
        **GOOGLE),
    "google_sheets": Provider(
        slug="google_sheets", name="Google Sheets", category="Productivity",
        base_url="https://sheets.googleapis.com/v4",
        scopes=("openid", "email", "profile",
                "https://www.googleapis.com/auth/spreadsheets"),
        **GOOGLE),
    "outlook": Provider(
        slug="outlook", name="Outlook", category="Communication",
        base_url="https://graph.microsoft.com/v1.0",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scopes=("openid", "email", "profile", "offline_access", "User.Read",
                "Mail.ReadWrite", "Mail.Send"),
        identity_url="https://graph.microsoft.com/v1.0/me",
        identity_json=("mail", "userPrincipalName", "displayName"),
        env=("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
        pkce=True,
        docs="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps",
    ),
    "onedrive": Provider(
        slug="onedrive", name="OneDrive", category="Storage",
        base_url="https://graph.microsoft.com/v1.0",
        authorize_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scopes=("openid", "email", "profile", "offline_access", "User.Read",
                "Files.ReadWrite.All"),
        identity_url="https://graph.microsoft.com/v1.0/me",
        identity_json=("mail", "userPrincipalName", "displayName"),
        env=("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
        pkce=True,
        docs="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps",
    ),
    "slack": Provider(
        slug="slack", name="Slack", category="Communication",
        base_url="https://slack.com/api",
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scopes=("channels:read", "chat:write", "files:write", "users:read", "team:read"),
        identity_url="https://slack.com/api/auth.test",
        identity_method="POST",
        identity_json=("user", "team"),
        revoke_url="https://slack.com/api/auth.revoke",
        env=("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET"),
        docs="https://api.slack.com/apps",
    ),
    "discord": Provider(
        slug="discord", name="Discord", category="Communication",
        base_url="https://discord.com/api/v10",
        authorize_url="https://discord.com/oauth2/authorize",
        token_url="https://discord.com/api/oauth2/token",
        scopes=("identify", "email", "guilds"),
        identity_url="https://discord.com/api/users/@me",
        identity_json=("username", "email"),
        revoke_url="https://discord.com/api/oauth2/token/revoke",
        revoke_mode="json",
        env=("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET"),
        authorize_params={"prompt": "consent"},
        docs="https://discord.com/developers/applications",
    ),
    "github": Provider(
        slug="github", name="GitHub", category="Developer",
        base_url="https://api.github.com",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scopes=("repo", "read:user", "user:email", "read:org"),
        identity_url="https://api.github.com/user",
        identity_json=("login", "email", "name"),
        revoke_url="https://api.github.com/applications/{client_id}/token",
        revoke_mode="basic",
        env=("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"),
        docs="https://github.com/settings/developers",
    ),
    "gitlab": Provider(
        slug="gitlab", name="GitLab", category="Developer",
        base_url="https://gitlab.com/api/v4",
        authorize_url="https://gitlab.com/oauth/authorize",
        token_url="https://gitlab.com/oauth/token",
        scopes=("read_user", "api"),
        identity_url="https://gitlab.com/api/v4/user",
        identity_json=("username", "email", "name"),
        revoke_url="https://gitlab.com/oauth/revoke",
        pkce=True,
        env=("GITLAB_CLIENT_ID", "GITLAB_CLIENT_SECRET"),
        docs="https://gitlab.com/-/user_settings/applications",
    ),
    "notion": Provider(
        slug="notion", name="Notion", category="Productivity",
        base_url="https://api.notion.com/v1",
        authorize_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        scopes=(),
        identity_url="https://api.notion.com/v1/users/me",
        identity_json=("name", "person.email", "bot.owner.user.name"),
        revoke_url="https://api.notion.com/v1/oauth/revoke",
        revoke_mode="json",
        env=("NOTION_CLIENT_ID", "NOTION_CLIENT_SECRET"),
        authorize_params={"owner": "user"},
        docs="https://www.notion.so/my-integrations",
    ),
    "linkedin": Provider(
        slug="linkedin", name="LinkedIn", category="Marketing",
        base_url="https://api.linkedin.com/v2",
        authorize_url="https://www.linkedin.com/oauth/v2/authorization",
        token_url="https://www.linkedin.com/oauth/v2/accessToken",
        scopes=("openid", "profile", "email", "w_member_social"),
        identity_url="https://api.linkedin.com/v2/userinfo",
        identity_json=("email", "name"),
        env=("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"),
        docs="https://www.linkedin.com/developers/apps",
    ),
    "dropbox": Provider(
        slug="dropbox", name="Dropbox", category="Storage",
        base_url="https://api.dropboxapi.com/2",
        authorize_url="https://www.dropbox.com/oauth2/authorize",
        token_url="https://api.dropboxapi.com/oauth2/token",
        scopes=("account_info.read", "files.metadata.read",
                "files.content.read", "files.content.write", "sharing.read"),
        identity_url="https://api.dropboxapi.com/2/users/get_current_account",
        identity_method="POST",
        identity_json=("email", "name.display_name"),
        revoke_url="https://api.dropboxapi.com/2/auth/token/revoke",
        revoke_mode="bearer",
        pkce=True,
        env=("DROPBOX_CLIENT_ID", "DROPBOX_CLIENT_SECRET"),
        authorize_params={"token_access_type": "offline"},
        docs="https://www.dropbox.com/developers/apps",
    ),
    "salesforce": Provider(
        slug="salesforce", name="Salesforce", category="CRM",
        base_url="https://login.salesforce.com/services/data/v60.0",
        authorize_url="https://login.salesforce.com/services/oauth2/authorize",
        token_url="https://login.salesforce.com/services/oauth2/token",
        scopes=("api", "refresh_token", "offline_access"),
        identity_url="https://login.salesforce.com/services/oauth2/userinfo",
        identity_json=("email", "preferred_username", "name"),
        revoke_url="https://login.salesforce.com/services/oauth2/revoke",
        env=("SALESFORCE_CLIENT_ID", "SALESFORCE_CLIENT_SECRET"),
        docs="https://help.salesforce.com/s/articleView?id=sf.connected_app_create.htm",
    ),
    "hubspot": Provider(
        slug="hubspot", name="HubSpot", category="CRM",
        base_url="https://api.hubapi.com",
        authorize_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/v1/token",
        scopes=("oauth", "crm.objects.contacts.read", "crm.objects.contacts.write",
                "crm.objects.companies.read", "crm.objects.deals.read"),
        identity_url="https://api.hubapi.com/oauth/v1/access-tokens/{token}",
        identity_json=("user", "hub_domain"),
        env=("HUBSPOT_CLIENT_ID", "HUBSPOT_CLIENT_SECRET"),
        docs="https://developers.hubspot.com/docs/api/oauth-quickstart-guide",
    ),
}

_ALIASES = {
    "google-mail": "gmail", "google_mail": "gmail", "gmail-api": "gmail",
    "google-drive": "google_drive", "google-calendar": "google_calendar",
    "google-sheets": "google_sheets", "googlecalendar": "google_calendar",
    "outlook-mail": "outlook", "microsoft-outlook": "outlook", "github-api": "github",
}


def provider_for(slug: str) -> Provider | None:
    key = (slug or "").strip().lower()
    return PROVIDERS.get(key) or PROVIDERS.get(_ALIASES.get(key, ""))


def credentials(provider: Provider) -> tuple[str, str]:
    """Platform-level client credentials for one provider."""
    from .oauth import stored_provider

    cid = os.getenv(provider.env[0], "").strip()
    secret = os.getenv(provider.env[1], "").strip()
    if cid and secret:
        return cid, secret
    stored = stored_provider(provider.slug) or {}
    if stored.get("client_id"):
        return stored["client_id"], stored.get("client_secret", "")
    return cid, secret


def ready(slug: str) -> bool:
    p = provider_for(slug)
    if p is None:
        return False
    cid, secret = credentials(p)
    return bool(cid and secret)


def managed_by_platform(slug: str) -> str:
    p = provider_for(slug)
    if p is None:
        return "catalog"
    if os.getenv(p.env[0], "").strip() and os.getenv(p.env[1], "").strip():
        return "environment"
    from .oauth import stored_provider

    return "console" if (stored_provider(p.slug) or {}).get("client_id") else "unconfigured"


def apply(spec: AppSpec) -> AppSpec:
    """Patch a catalog app so its auth metadata is the curated, working one."""
    p = provider_for(spec.slug)
    if p is None:
        return spec
    spec.auth = AuthSpec(
        type="oauth2",
        authorize_url=p.authorize_url,
        token_url=p.token_url,
        scopes=list(p.scopes) if p.scopes else list(spec.auth.scopes),
        client_id_env=p.env[0],
        client_secret_env=p.env[1],
        pkce=p.pkce or spec.auth.pkce,
        authorize_params={**(spec.auth.authorize_params or {}), **p.authorize_params},
        token_params={**(spec.auth.token_params or {}), **p.token_params},
        header_name=spec.auth.header_name or "Authorization",
        value_template=spec.auth.value_template or "Bearer {token}",
        static_env=spec.auth.static_env,
    )
    if p.base_url and not spec.base_url:
        spec.base_url = p.base_url
    if not spec.docs and p.docs:
        spec.docs = p.docs
    return spec


_ONEDRIVE_ACTIONS = (
    ("list_files", "List files", "GET", "/me/drive/root/children",
     {"path": {"type": "string", "in": "query", "description": "Folder path, optional"}}, "read"),
    ("search_files", "Search files", "GET", "/me/drive/root/search(q='{query}')",
     {"query": {"type": "string", "in": "path", "required": True,
                "description": "Text to look for in file names"}}, "read"),
    ("upload_file", "Upload a file", "PUT", "/me/drive/root:/{path}:/content",
     {"path": {"type": "string", "in": "path", "required": True, "description": "Destination path"},
      "content": {"type": "string", "in": "body", "required": True, "description": "File text"}}, "write"),
)


def ensure_apps(cat: Any) -> list[str]:
    """Add catalog entries for managed providers the catalog does not ship yet."""
    added: list[str] = []
    if "onedrive" in getattr(cat, "apps", {}):
        return added
    p = PROVIDERS["onedrive"]
    actions = [
        ActionSpec(slug=s, name=n, description=n, method=m, url=f"{p.base_url}{path}",
                   params=params, required=[k for k, v in params.items() if v.get("required")],
                   tier=tier)
        for s, n, m, path, params, tier in _ONEDRIVE_ACTIONS
    ]
    spec = AppSpec(
        slug="onedrive", name=p.name, category=p.category,
        description="Files in Microsoft OneDrive, through Microsoft Graph. Sign in with Microsoft.",
        docs=p.docs, logo="https://cdn.simpleicons.org/microsoftonedrive/0078D4",
        auth=AuthSpec(type="oauth2"), actions=actions, base_url=p.base_url,
        source="managed", popular=True,
    )
    cat.apps["onedrive"] = apply(spec)
    added.append("onedrive")
    return added
