import ipaddress
import math
from typing import Annotated

from pydantic import Field

# A UDP port number; 0 is not a usable destination and >65535 overflows sendto.
Port = Annotated[int, Field(ge=1, le=65535)]


def finite_float(v) -> float:
    """``v`` (typed text or a number) as a float, or ValueError when it is not a finite
    number. float() also parses "nan" and "inf", which no setting can use: NaN never
    equals itself, so a page would see it as a change on every tick."""
    try:
        value = float(v.strip() if isinstance(v, str) else v)
    except (TypeError, ValueError):
        raise ValueError("Please provide a proper number")
    if not math.isfinite(value):
        raise ValueError("Please provide a proper number")
    return value


def check_is_float_convertible(v: str):
    """
    Check if value provided can be converted to a finite float or double.

    Settings entries hold free text, so we have to make sure that what the user
    typed in is a valid number
    """
    finite_float(v)
    return v


def try_convert_to_float(v: str):
    """
    Check if value provided can be converted to a float and return converted result
    Basically what `check_is_float_convertible` does but returns a float
    """
    return finite_float(v)


def check_is_ip_address(v: str):
    try:
        ipaddress.IPv4Address(v)
        return v
    except ValueError:
        raise ValueError("Please provide a valid IP Address")
