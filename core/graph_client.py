"""Microsoft Graph authentication (Phase: Graph Integration).

Builds an authenticated `msgraph.GraphServiceClient`, scoped to a specific
*customer* tenant rather than our own. We're a multi-tenant Azure Marketplace
SaaS app (`MicrosoftAppId`/`MicrosoftAppPassword` from `.env`, see
`api/main.py`'s `DefaultConfig`); each customer's SharePoint lives in their
own Azure AD tenant (`tenants.azure_customer_tenant_id`, see `db/models.py`),
and we can only read it once that customer's admin has granted our app
consent there (e.g. the `Sites.Read.All` application permission) -- so every
Graph call must authenticate against that tenant, never our own
`MicrosoftAppTenantId`.

Confirmed against the installed `msgraph-sdk`/`azure-identity` versions:
`GraphServiceClient` accepts a synchronous `azure.identity.ClientSecretCredential`
directly (it also accepts the `.aio` async variant, but the sync one is
simpler and every SDK call site is already `async def` regardless -- the
credential itself doesn't need to be async to work here).
"""

from __future__ import annotations

import os

from azure.identity import ClientSecretCredential
from msgraph import GraphServiceClient

# Application-permission app-only token; `.default` means "whatever
# application permissions an admin has already consented to for this app in
# this tenant" (e.g. Sites.Read.All) -- no per-scope negotiation at runtime.
GRAPH_SCOPES: list[str] = ["https://graph.microsoft.com/.default"]


def build_graph_client(customer_tenant_id: str) -> GraphServiceClient:
    """Build a `GraphServiceClient` authenticated into `customer_tenant_id`.

    One client per (customer tenant, sync run) -- cheap to construct (no
    network call happens until the first request triggers token acquisition),
    and each `GraphServiceClient` owns its own `httpx.AsyncClient`, so there's
    no risk of one tenant's credential leaking into another's requests via a
    shared client instance.

    Raises `KeyError` if `MicrosoftAppId`/`MicrosoftAppPassword` aren't set --
    fail fast rather than construct a credential that will only fail later,
    deep inside a Graph call, with a confusing 401.
    """
    credential = ClientSecretCredential(
        tenant_id=customer_tenant_id,
        client_id=os.environ["MicrosoftAppId"],
        client_secret=os.environ["MicrosoftAppPassword"],
    )
    return GraphServiceClient(credentials=credential, scopes=GRAPH_SCOPES)
