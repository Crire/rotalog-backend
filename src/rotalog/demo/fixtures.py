"""Dataset V1 fictício; UUID4 fixos tornam o seed idempotente."""

from decimal import Decimal
from uuid import UUID

DEMO_RUN_ID = UUID("02699c03-3036-43dc-83f0-32521d1b029b")
DEMO_NAME = "pitch-v1-sintetico"
USERS = (
    (UUID("ef7d0b9b-a203-4296-805e-c985ba16fba0"), "comprador", "Mercado Sintético"),
    (
        UUID("c4c3c853-3d03-4cec-8c43-bcbe50e614ed"),
        "fornecedor",
        "Distribuidora Sintética",
    ),
    (
        UUID("b3e6074b-5481-4d99-a9c6-86956fafaa4a"),
        "motorista",
        "Transportadora Sintética",
    ),
)
PRODUCTS = (
    (
        UUID("d5c1345c-17d8-49d8-94c4-39650dce3583"),
        "Arroz — fardo 6 × 5 kg",
        Decimal("149.90"),
    ),
    (
        UUID("d3b89452-589c-4c39-a52a-38d22e2b1380"),
        "Feijão — fardo 10 × 1 kg",
        Decimal("79.50"),
    ),
    (
        UUID("8db7bd27-23fd-492e-a55f-6eaf6cc088ce"),
        "Açúcar — fardo 10 × 1 kg",
        Decimal("45.00"),
    ),
    (
        UUID("37dd0882-f512-4ec5-9da6-064dd6cb7796"),
        "Óleo — caixa 20 × 900 ml",
        Decimal("139.80"),
    ),
)
