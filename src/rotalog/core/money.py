"""BRL: inteiros em centavos no domínio; strings decimais no contrato HTTP."""

from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, PlainSerializer


def _decimal_string(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("Informe dinheiro como string decimal, nunca float")  # noqa: TRY004 - Pydantic requer ValueError
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError("Valor monetário inválido") from exc
    if not result.is_finite() or result < 0 or result > Decimal("999999999999.99"):
        raise ValueError("Valor monetário fora dos limites")
    if result != result.quantize(Decimal("0.01")):
        raise ValueError("Use valor não negativo com até duas casas decimais")
    return result


MoneyInput = Annotated[
    Decimal,
    BeforeValidator(_decimal_string, json_schema_input_type=str),
    Field(ge=0, max_digits=14, decimal_places=2),
    PlainSerializer(lambda value: format(value, ".2f"), return_type=str),
]


def minor(value: Decimal) -> int:
    return int(value * 100)


def decimal_string(amount_minor: int) -> str:
    return format(Decimal(amount_minor) / 100, ".2f")
