import logging
import aiohttp
from typing import Any, Dict, Optional

_LOGGER = logging.getLogger(__name__)
#_LOGGER.setLevel(logging.DEBUG)  # Ensure debug-level messages are logged

MAX_TX_PER_PAGE = 50               # page size for /transactions
BASE_URL = "https://api.up.com.au/api/v1"

class UP:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def call(self, endpoint, method="get", params=None, json=None):
        if params is None:
            params = {}

        _LOGGER.debug(f"Making {method.upper()} request to {BASE_URL + endpoint} with headers: {self._session.headers} and params: {params} and json: {json}")
        
        #async with async_get_clientsession(headers=headers) as session:
        # todo: add other branch to utilise clientsession from HA ^^
        try:
            async with self._session.request(method=method, url=BASE_URL + endpoint, params=params, json=json) as resp:
                _LOGGER.debug(f"Received response status: {resp.status}")
                
                if resp.status == 401:
                    _LOGGER.error("Unauthorized: Invalid API Key")
                    return None
                if resp.status not in {200, 201, 204}:
                    _LOGGER.error(f"Error: Received status code {resp.status}")
                    return None
                
                response_data = await resp.json()
                _LOGGER.debug(f"Response JSON: {response_data}")
                return response_data
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Network error occurred: {e}")
            return None

    async def create_webhook(self, callback_url: str) -> str:
        data = {
            "data": {
                "attributes": {
                    "url": callback_url,
                    "description": "Home Assistant"
                }
            }
        }
        resp = await self.call("/webhooks", method="post", params=None, json=data)
        return resp["data"]

    async def webhook_exists(self, webhook_id: str) -> bool:
        resp = await self.call(f"/webhooks/{webhook_id}/ping", method="post")
        return resp != None

    async def list_webhooks(self) -> str:
        response = await self.call(f"/webhooks")
        return response

    async def delete_webhook(self, webhook_id: str) -> bool:
        response = await self.call(f"/webhooks/{webhook_id}", method= "delete")
        return response != None

    async def get_accounts(self) -> Dict[str, Any]:
        return await self.call("/accounts")
    
    async def get_account(self, accountID: str) -> Dict[str, Any]:
        return await self.call(f"/accounts/{accountID}")

    async def get_transactions(self, page_size: int = MAX_TX_PER_PAGE) -> Dict[str, Any]:
        # Most recent first; one page is plenty for dashboards & notifications.
        return await self.call("/transactions", params={"page[size]": str(page_size)})

    async def get_categories(self) -> Dict[str, Any]:
        return await self.call("/categories")

    async def get_tags(self) -> Dict[str, Any]:
        return await self.call("/tags")
    
    async def ping(self) -> bool:
        return await self.call("/util/ping") != None
