from __future__ import annotations
from datetime import timedelta
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from up import UP

_LOGGER = logging.getLogger(__name__)

MAX_TX_PER_PAGE = 50 # page size for /transactions

class UpDataCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Fetch accounts, recent transactions, categories, tags on a schedule. Handle partial refreshes trigggered by webhook events"""

    def __init__(self, hass: HomeAssistant, api: UP, update_interval: timedelta = 5) -> None:
        super().__init__(
            hass, 
            _LOGGER, 
            name="Up Bank Coordinator", 
            update_interval=update_interval,
        )
        self.api = api

    async def _async_update_data(self) -> Dict[str, Any]:
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

        # Compute total balance safely
        total = 0.0
        for a in accounts:
            try:
                total += float(a["attributes"]["balance"]["value"])
            except Exception:
                continue

        return {
            "accounts": accounts,
            "transactions": transactions,
            "categories": categories,
            "tags": tags,
            "summary": {
                "total_balance": total,
                "account_count": len(accounts),
                "transaction_count": len(transactions),
            },
        }
    
    async def _async_partial_refresh_data(self, transactionID: str) -> Dict[str, Any]:

        try:
            transaction = await self.api.call(f"/transactions/{transactionID}")
        except Exception as exc:
            raise UpdateFailed(f"Error fetching Up data: {exc}") from exc
        
        if transaction != None:
            refresh_accounts = []
            transaction_account = transaction["data"]["relationships"]["account"]["data"]

            refresh_accounts.append(transaction_account["id"])

            transfer_account = transaction["data"]["relationships"]["transferAccount"]["data"]

            if transfer_account != None:
                refresh_accounts.append(transfer_account["id"])

            accounts_data = {"data" : []}
            try: 
                for account in refresh_accounts:
                    accounts_resp = await self.api.get_account(account)
                    accounts_data["data"].append(accounts_resp["data"])\
                    
            except Exception as exc:
                raise UpdateFailed(f"Error fetching Up data: {exc}") from exc
            
            tx_resp = {"data" : [transaction["data"]]}
        
            accounts = accounts_data.get("data") or []
            transactions = tx_resp.get("data") or []
        
            return {
                    "accounts": accounts,
                    "transactions": transactions,
                    },