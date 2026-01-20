# MesaYA Payment Microservice

Microservicio de pagos para MesaYA que implementa el **Pilar 2: Webhooks e Interoperabilidad B2B**.

## Características

- 💳 **Múltiples Pasarelas de Pago**: Stripe, MercadoPago, Mock (desarrollo)
- 🔐 **Webhooks Seguros**: Firma HMAC-SHA256 para verificación
- 🤝 **B2B Partner Integration**: Sistema de partners con webhooks bidireccionales
- 📊 **Analytics**: Estadísticas de pagos por reserva/suscripción
- 🔄 **Idempotencia**: Soporte para requests idempotentes

## Arquitectura

```
mesaYA_payment_ms/
├── src/
│   └── mesaYA_payment_ms/
│       ├── __init__.py
│       ├── __main__.py
│       ├── app.py                 # FastAPI application
│       ├── features/
│       │   ├── payments/          # Payment domain
│       │   │   ├── application/   # Use cases
│       │   │   ├── domain/        # Entities, VOs
│       │   │   ├── infrastructure/# Repositories, Adapters
│       │   │   └── presentation/  # Controllers, DTOs
│       │   ├── webhooks/          # Webhook handlers
│       │   └── partners/          # B2B partners
│       └── shared/
│           ├── core/              # Config, DI
│           ├── domain/            # Shared types
│           └── infrastructure/    # Shared adapters
├── tests/
├── pyproject.toml
└── Dockerfile
```

## Endpoints

### Payments

| Method | Endpoint                         | Description                   |
| ------ | -------------------------------- | ----------------------------- |
| POST   | `/api/payments`                  | Crear nuevo pago              |
| GET    | `/api/payments/{id}`             | Obtener pago por ID           |
| POST   | `/api/payments/{id}/verify`      | Verificar estado con provider |
| POST   | `/api/payments/{id}/cancel`      | Cancelar pago pendiente       |
| POST   | `/api/payments/{id}/refund`      | Reembolsar pago completado    |
| GET    | `/api/payments/reservation/{id}` | Pagos de una reserva          |

### Webhooks

| Method | Endpoint                | Description                     |
| ------ | ----------------------- | ------------------------------- |
| POST   | `/api/webhooks/stripe`  | Webhook de Stripe               |
| POST   | `/api/webhooks/mock`    | Webhook de Mock (dev)           |
| POST   | `/api/webhooks/partner` | Webhook entrante de partner B2B |

### Partners (B2B)

| Method | Endpoint                           | Description             |
| ------ | ---------------------------------- | ----------------------- |
| POST   | `/api/partners/register`           | Registrar nuevo partner |
| GET    | `/api/partners`                    | Listar partners activos |
| PATCH  | `/api/partners/{id}`               | Actualizar partner      |
| POST   | `/api/partners/{id}/rotate-secret` | Rotar secret HMAC       |

## Instalación

```bash
# Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -e ".[dev]"

# Copiar variables de entorno
cp .env.template .env

# Ejecutar
uvicorn mesaYA_payment_ms.app:app --reload --port 8003
```

## Patrón Adapter para Pasarelas

```python
from abc import ABC, abstractmethod

class PaymentProviderPort(ABC):
    @abstractmethod
    async def create_payment_intent(self, request: CreatePaymentRequest) -> PaymentIntent:
        pass

    @abstractmethod
    async def verify_payment(self, provider_payment_id: str) -> PaymentStatus:
        pass

    @abstractmethod
    async def refund_payment(self, provider_payment_id: str) -> RefundResult:
        pass
```

## Eventos de Webhook

```python
class WebhookEventType(str, Enum):
    PAYMENT_CREATED = "payment.created"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"
    RESERVATION_PAID = "reservation.paid"
```

## Variables de Entorno

Ver `.env.template` para la lista completa de variables requeridas.

## Testing

```bash
# Ejecutar tests
pytest

# Con cobertura
pytest --cov=mesaYA_payment_ms
```
