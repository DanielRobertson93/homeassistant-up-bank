from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

MAX_TX_PER_PAGE = 50  # page size for /transactions
MAX_PAGE_SIZE = 100  # Up's documented max page[size]
BASE_URL = "https://api.up.com.au/api/v1"


class UP:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def call(
        self,
        endpoint: str,
        method: str = "get",
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if params is None:
            params = {}

        # Pagination links from Up are already full URLs; everything else is a relative endpoint.
        url = endpoint if endpoint.startswith("http") else BASE_URL + endpoint

        _LOGGER.debug(
            "Making %s request to %s with params: %s", method.upper(), url, params
        )

        try:
            async with self._session.request(
                method=method, url=url, headers=self._headers, params=params, json=json
            ) as resp:
                _LOGGER.debug("Received response status: %s", resp.status)

                if resp.status == 401:
                    _LOGGER.error("Unauthorized: Invalid API Key")
                    return None
                if resp.status not in {200, 201, 204}:
                    body = await resp.text()
                    _LOGGER.error(
                        "Error: Received status code %s: %s", resp.status, body
                    )
                    return None

                if (
                    method == "delete"
                ):  # delete does not return content, so return empty dict
                    return {}

                response_data = await resp.json()
                _LOGGER.debug("Response JSON: %s", response_data)
                return response_data
        except aiohttp.ClientError as e:
            _LOGGER.error("Network error occurred: %s", e)
            return None

    async def create_webhook(self, callback_url: str) -> dict[str, Any]:
        data = {
            "data": {
                "attributes": {"url": callback_url, "description": "Home Assistant"}
            }
        }
        resp = await self.call("/webhooks", method="post", json=data)
        if resp is None:
            raise RuntimeError(
                f"Up API rejected webhook creation for callback URL {callback_url}"
            )
        return resp["data"]

    async def webhook_exists(self, webhook_id: str) -> bool:
        resp = await self.call(f"/webhooks/{webhook_id}/ping", method="post")
        return resp is not None

    async def list_webhooks(self) -> dict[str, Any] | None:
        return await self.call("/webhooks")

    async def delete_webhook(self, webhook_id: str) -> bool:
        response = await self.call(f"/webhooks/{webhook_id}", method="delete")
        return response is not None

    async def get_accounts(self) -> dict[str, Any] | None:
        return await self.call("/accounts")

    async def get_account(self, account_id: str) -> dict[str, Any] | None:
        return await self.call(f"/accounts/{account_id}")

    async def get_transactions(
        self, page_size: int = MAX_TX_PER_PAGE
    ) -> dict[str, Any] | None:
        # Most recent first; one page is plenty for dashboards & notifications.
        return await self.call("/transactions", params={"page[size]": str(page_size)})

    async def get_transactions_since(
        self, since_iso: str
    ) -> list[dict[str, Any]] | None:
        """Fetch every transaction from `since_iso` to now, following pagination.

        Bounded by how many transactions occurred in that window (not full account
        history), so this stays cheap for e.g. "since start of month" style queries.
        """
        resp = await self.call(
            "/transactions",
            params={"filter[since]": since_iso, "page[size]": str(MAX_PAGE_SIZE)},
        )
        if resp is None:
            return None

        transactions: list[dict[str, Any]] = []
        while resp is not None:
            transactions.extend(resp.get("data") or [])
            next_url = (resp.get("links") or {}).get("next")
            if not next_url:
                break
            resp = await self.call(next_url)

        return transactions

    async def get_categories(self) -> dict[str, Any] | None:
        return await self.call("/categories")

    async def get_tags(self) -> dict[str, Any] | None:
        return await self.call("/tags")

    async def ping(self) -> bool:
        ping_response = await self.call("/util/ping")
        if ping_response is not None:
            return ping_response["meta"]["statusEmoji"] == "⚡️"
        else:
            return False
