"""HTTP clients for external services."""

from mesaYA_payment_ms.shared.infrastructure.http_clients.mesa_ya_res_client import (
    MesaYaResClient,
    PartnerInfo,
    get_mesa_ya_res_client,
)

__all__ = ["MesaYaResClient", "PartnerInfo", "get_mesa_ya_res_client"]
