"""Keep numeric tokens stable across parsing and source-text serialization."""

from decimal import Decimal, InvalidOperation
import math


def parse_float_token(token: str) -> float:
    """Accept a float only if its rendered decimal value preserves the input.

    The IR uses ordinary JSON numbers. Reject underflow and excess precision
    instead of silently changing the source token during float roundtripping.
    Equivalent decimal spellings (0.10, .1, 1e-1) remain acceptable.
    """
    number = float(token)
    if not math.isfinite(number):
        raise ValueError("non-finite or overflowing numeric token")
    try:
        original = Decimal(token)
        rendered = Decimal(str(number))
    except InvalidOperation as exc:
        raise ValueError("number exceeds the supported numeric range") from exc
    if original != rendered:
        if number == 0:
            raise ValueError("nonzero number underflows the supported numeric range")
        raise ValueError("numeric precision cannot be preserved by this IR")
    return number
