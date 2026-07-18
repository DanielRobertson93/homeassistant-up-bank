from __future__ import annotations
from datetime import timedelta
import asyncio
import logging
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from .up import UP

_LOGGER = logging.getLogger(__name__)

MAX_TX_PER_PAGE = 50 # page size for /transactions

class UpDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch accounts, recent transactions, categories, tags on a schedule. Handle partial refreshes trigggered by webhook events"""

    def __init__(self, hass: HomeAssistant, api: UP, update_interval: timedelta = 5) -> None:
        super().__init__(
            hass, 
            _LOGGER, 
            name="Up Bank Coordinator", 
            update_interval=update_interval,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            # Fetch concurrently while staying very cheap (4 requests per cycle).
            accounts_resp, tx_resp, cats_resp, tags_resp = await asyncio.gather(
                self.api.get_accounts(),
                self.api.get_transactions(page_size=MAX_TX_PER_PAGE),
                self.api.get_categories(),
                self.api.get_tags(),
            )
        except Exception as exc:
            raise UpdateFailed(f"Error fetching Up data: {exc}") from exc

        accounts = accounts_resp.get("data") or []
        transactions = tx_resp.get("data") or []
        categories = cats_resp.get("data") or []
        tags = tags_resp.get("data") or []

        return {
            "accounts": accounts,
            "transactions": transactions,
            "categories": categories,
            "tags": tags,
            "summary": self._summarize(accounts, transactions),
        }

    @staticmethod
    def _summarize(accounts: list, transactions: list) -> dict[str, Any]:
        total = 0.0
        for a in accounts:
            try:
                total += float(a["attributes"]["balance"]["value"])
            except Exception:
                continue
        return {
            "total_balance": total,
            "account_count": len(accounts),
            "transaction_count": len(transactions),
        }

    async def _async_partial_refresh_data(self, transaction_id: str) -> dict[str, Any]:
        """Refresh only the accounts and transaction touched by a webhook event.

        Merges into the existing dataset rather than replacing it, so
        categories/tags/other transactions survive a partial refresh.
        """
        try:
            transaction_resp = await self.api.call(f"/transactions/{transaction_id}")
        except Exception as exc:
            raise UpdateFailed(f"Error fetching Up transaction: {exc}") from exc

        if transaction_resp is None:
            raise UpdateFailed(f"Up transaction {transaction_id} not found")

        try:
            transaction = transaction_resp["data"]
            relationships = transaction["relationships"]

            account_ids = [relationships["account"]["data"]["id"]]
            transfer_account = (relationships.get("transferAccount") or {}).get("data")
            if transfer_account is not None:
                account_ids.append(transfer_account["id"])
        except KeyError as exc:
            raise UpdateFailed(f"Unexpected Up transaction payload shape: {exc}") from exc

        try:
            refreshed_accounts = {
                account_id: (await self.api.get_account(account_id))["data"]
                for account_id in account_ids
            }
        except Exception as exc:
            raise UpdateFailed(f"Error fetching Up account: {exc}") from exc

        data = dict(self.data or {})
        accounts = {a["id"]: a for a in data.get("accounts", [])}
        accounts.update(refreshed_accounts)

        transactions = [t for t in data.get("transactions", []) if t["id"] != transaction["id"]]
        transactions.insert(0, transaction)

        accounts_list = list(accounts.values())
        data.update({
            "accounts": accounts_list,
            "transactions": transactions,
            "summary": self._summarize(accounts_list, transactions),
        })
        return data