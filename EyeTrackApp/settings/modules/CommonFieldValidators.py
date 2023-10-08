def check_is_float_convertible(v: str):
    """Check if value provided can be converted to a float or double.

        PySimpleGUI does not support floats or doubles in UI, so we have to make sure
        that what the user typed in is correct
    """
    try:
        float(v)
        return v
    except ValueError:
        raise ValueError("Please provide a proper number")
