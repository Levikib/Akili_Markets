"""
Deriv REST API auth — fetches accounts and OTP for WebSocket authentication.
Uses the new api.derivws.com REST API with PAT token.
"""
import httpx
from loguru import logger
from app.core.config import settings

DERIV_REST_BASE = "https://api.derivws.com"


class DerivAuth:
    def __init__(self):
        self._headers = {
            "Authorization": f"Bearer {settings.deriv_api_token}",
            "Deriv-App-ID": settings.deriv_app_id,
            "Content-Type": "application/json",
        }
        self._demo_account_id: str = ""
        self._real_account_id: str = ""
        self._demo_balance: float = 0.0

    async def fetch_accounts(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{DERIV_REST_BASE}/trading/v1/options/accounts",
                headers=self._headers,
            )
            r.raise_for_status()
            accounts = r.json()["data"]
            for acc in accounts:
                if acc["account_type"] == "demo":
                    self._demo_account_id = acc["account_id"]
                    self._demo_balance = float(acc["balance"])
                elif acc["account_type"] == "real":
                    self._real_account_id = acc["account_id"]
            logger.info(f"Accounts loaded — Demo: {self._demo_account_id} (${self._demo_balance}) | Real: {self._real_account_id}")
            return accounts

    async def get_ws_url(self, use_real: bool = False) -> str:
        """Get a fresh OTP-authenticated WebSocket URL. OTPs are single-use."""
        account_id = self._real_account_id if use_real else self._demo_account_id
        if not account_id:
            await self.fetch_accounts()
            account_id = self._real_account_id if use_real else self._demo_account_id

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{DERIV_REST_BASE}/trading/v1/options/accounts/{account_id}/otp",
                headers=self._headers,
            )
            r.raise_for_status()
            url = r.json()["data"]["url"]
            mode = "REAL" if use_real else "DEMO"
            logger.info(f"WebSocket OTP obtained for {mode} account {account_id}")
            return url

    @property
    def demo_account_id(self) -> str:
        return self._demo_account_id

    @property
    def real_account_id(self) -> str:
        return self._real_account_id

    @property
    def demo_balance(self) -> float:
        return self._demo_balance


deriv_auth = DerivAuth()
