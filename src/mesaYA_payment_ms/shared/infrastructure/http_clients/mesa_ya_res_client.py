"""HTTP client for communicating with mesaYA_Res API."""

from dataclasses import dataclass
from typing import Any

import httpx

from mesaYA_payment_ms.shared.core.settings import get_settings


@dataclass
class PartnerInfo:
    """Partner information from mesaYA_Res."""

    id: str
    name: str
    webhook_url: str
    secret: str
    subscribed_events: list[str]
    status: str
    contact_email: str | None = None
    description: str | None = None


class MesaYaResClient:
    """
    HTTP client for mesaYA_Res API.

    Used to fetch partner information for webhook dispatching.
    Partners are managed in mesaYA_Res, and Payment MS fetches them
    when it needs to send webhooks.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.mesa_ya_res_url
        self._timeout = 10.0

    async def get_partners_for_event(self, event_type: str) -> list[PartnerInfo]:
        """
        Fetch all active partners subscribed to a specific event.

        Args:
            event_type: The webhook event type (e.g., 'payment.succeeded')

        Returns:
            List of partners subscribed to the event
        """
        # mesaYA_Res partners endpoint is versioned at /api/v1/partners
        url = f"{self._base_url}/api/v1/partners"

        print(f"🔍 Fetching partners from {url} for event: {event_type}")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    params={"subscribedEvent": event_type, "status": "active"},
                    headers={"Content-Type": "application/json"},
                )

                print(f"📡 Partners API response status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    print(f"📦 Partners API raw response: {data}")

                    partners_data = (
                        data.get("data", data) if isinstance(data, dict) else data
                    )

                    if isinstance(partners_data, list):
                        partners = [
                            PartnerInfo(
                                id=p.get("id", ""),
                                name=p.get("name", ""),
                                webhook_url=p.get("webhookUrl", ""),
                                secret=p.get("secret", ""),
                                # Field is "events" in API response, not "subscribedEvents"
                                subscribed_events=p.get(
                                    "events", p.get("subscribedEvents", [])
                                ),
                                status=p.get("status", "active"),
                                contact_email=p.get("contactEmail"),
                                description=p.get("description"),
                            )
                            for p in partners_data
                        ]
                        print(
                            f"✅ Found {len(partners)} partners for event {event_type}"
                        )
                        for p in partners:
                            print(
                                f"   - {p.name}: {p.webhook_url} (events: {p.subscribed_events})"
                            )
                        return partners

                    print(f"⚠️ Unexpected response format from mesaYA_Res: {data}")
                    return []
                else:
                    print(
                        f"⚠️ Failed to fetch partners: {response.status_code} - {response.text}"
                    )
                    return []

        except httpx.TimeoutException:
            print(f"⏱️ Timeout fetching partners from mesaYA_Res")
            return []
        except httpx.RequestError as e:
            print(f"❌ Error fetching partners from mesaYA_Res: {e}")
            return []

    async def get_all_active_partners(self) -> list[PartnerInfo]:
        """
        Fetch all active partners.

        Returns:
            List of all active partners
        """
        url = f"{self._base_url}/api/v1/partners"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    params={"status": "active"},
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    data = response.json()
                    partners_data = (
                        data.get("data", data) if isinstance(data, dict) else data
                    )

                    if isinstance(partners_data, list):
                        return [
                            PartnerInfo(
                                id=p.get("id", ""),
                                name=p.get("name", ""),
                                webhook_url=p.get("webhookUrl", ""),
                                secret=p.get("secret", ""),
                                # Field is "events" in API response, not "subscribedEvents"
                                subscribed_events=p.get(
                                    "events", p.get("subscribedEvents", [])
                                ),
                                status=p.get("status", "active"),
                                contact_email=p.get("contactEmail"),
                                description=p.get("description"),
                            )
                            for p in partners_data
                        ]
                    return []
                else:
                    print(f"⚠️ Failed to fetch partners: {response.status_code}")
                    return []

        except httpx.TimeoutException:
            print(f"⏱️ Timeout fetching partners from mesaYA_Res")
            return []
        except httpx.RequestError as e:
            print(f"❌ Error fetching partners from mesaYA_Res: {e}")
            return []

    async def notify_payment_status(
        self,
        payment_id: str,
        status: str,
        reservation_id: str | None = None,
    ) -> bool:
        """
        Notify mesaYA_Res about a payment status change.

        This allows mesaYA_Res to update reservation status, etc.

        Args:
            payment_id: The payment ID
            status: The new payment status
            reservation_id: Optional reservation ID

        Returns:
            True if notification was successful
        """
        url = f"{self._base_url}/api/v1/payment-gateway/{payment_id}/status-callback"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "payment_id": payment_id,
                        "status": status,
                        "reservation_id": reservation_id,
                    },
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code < 300:
                    print(
                        f"✅ Notified mesaYA_Res about payment {payment_id} status: {status}"
                    )
                    return True
                else:
                    print(f"⚠️ Failed to notify mesaYA_Res: {response.status_code}")
                    return False

        except Exception as e:
            print(f"❌ Error notifying mesaYA_Res: {e}")
            return False


# Singleton instance
_client: MesaYaResClient | None = None


def get_mesa_ya_res_client() -> MesaYaResClient:
    """Get singleton mesaYA_Res client instance."""
    global _client
    if _client is None:
        _client = MesaYaResClient()
    return _client
