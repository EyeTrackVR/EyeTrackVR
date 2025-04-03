import ipaddress


def check_is_float_convertible(v: str):
    """
    Check if value provided can be converted to a float or double.

    PySimpleGUI does not support floats or doubles in UI, so we have to make sure
    that what the user typed in is correct
    """
    try:
        float(v)
        return v
    except ValueError:
        raise ValueError("Please provide a proper number")


def try_convert_to_float(v: str):
    """
    Check if value provided can be converted to a float and return converted result
    Basically what `check_is_float_convertible` does but returns a float
    """
    try:
        return float(check_is_float_convertible(v))
    except ValueError:
        raise


def check_is_ip_address(v: str):
    try:
        ipaddress.IPv4Address(v)
        return v
    except ValueError:
        raise ValueError("Please provide a valid IP Address")
