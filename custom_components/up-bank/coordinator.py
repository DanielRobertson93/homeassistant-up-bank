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
from homeassistant.util import dt as dt_util
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

        summary = self._summarize(accounts)
        summary.update(await self._fetch_window_counts())

        return {
            "accounts": accounts,
            "transactions": transactions,
            "categories": categories,
            "tags": tags,
            "summary": summary,
        }

    @staticmethod
    def _summarize(accounts: list) -> dict[str, Any]:
        total = 0.0
        for a in accounts:
            try:
                total += float(a["attributes"]["balance"]["value"])
            except Exception:
                continue
        return {
            "total_balance": total,
            "account_count": len(accounts),
        }

    async def _fetch_window_counts(self) -> dict[str, int]:
        """Count transactions today / this week / this month.

        One bounded fetch since the start of the month covers all three windows -
        cheap regardless of account age, unlike walking full transaction history.
        """
        now = dt_util.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=now.weekday())
        start_of_month = start_of_today.replace(day=1)

        previous = (self.data or {}).get("summary", {})
        fallback = {
            key: previous.get(key, 0)
            for key in ("transactions_today", "transactions_this_week", "transactions_this_month")
        }

        try:
            month_transactions = await self.api.get_transactions_since(start_of_month.isoformat())
        except Exception:
            month_transactions = None

        if month_transactions is None:
            _LOGGER.warning("Failed fetching transaction window counts; keeping previous values")
            return fallback

        today_count = 0
        week_count = 0
        for tx in month_transactions:
            created = dt_util.parse_datetime(tx["attributes"]["createdAt"])
            if created is None or created < start_of_week:
                continue
            week_count += 1
            if created >= start_of_today:
                today_count += 1

        return {
            "transactions_today": today_count,
            "transactions_this_week": week_count,
            "transactions_this_month": len(month_transactions),
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
        summary = self._summarize(accounts_list)
        summary.update(await self._fetch_window_counts())

        data.update({
            "accounts": accounts_list,
            "transactions": transactions,
            "summary": summary,
        })
        return data