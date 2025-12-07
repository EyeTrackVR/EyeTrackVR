# Config Validation Fix - Integer 0 Values

## Issue Reported by @m-RNA

When `eyetrack_settings.json` contained integer values `"calib_axes": 0` and `"calib_evecs": 0`, the application would crash on startup with a Pydantic validation error.

### Example Problematic Config

```json
{
    "right_eye": {
        "calib_axes": 0,
        "calib_evecs": 0,
        "calib_XOFF": 74.36,
        "calib_YOFF": 36.55,
        ...
    }
}
```

### Error

```
Traceback (most recent call last):
  File "eyetrackapp.py", line 501, in <module>
    main()
  ...
pydantic.ValidationError: 2 validation errors for EyeTrackCameraConfig
calib_axes
  Input should be a valid list [type=list_type, input_value=0, input_type=int]
calib_evecs
  Input should be a valid list [type=list_type, input_value=0, input_type=int]
```

## Root Cause

1. **How it happened**: Previous calibration bugs could save integer `0` instead of arrays
2. **Why it crashed**: Pydantic expected `Union[List[float], None]` but got `int`
3. **Where it failed**: During config loading at startup

## Solution

### Part 1: Field Validator (config.py)

Added a check in the field validator to convert invalid scalar values to `None`:

```python
@field_validator('calib_axes', 'calib_evecs', 'calib_center', mode='before')
@classmethod
def convert_numpy_to_list(cls, v):
    """Convert NumPy arrays to lists and handle invalid values"""
    if v is None:
        return None
    # Handle invalid scalar values (e.g., integer 0 from corrupted config files)
    # These should be treated as None (uncalibrated)
    if isinstance(v, (int, float)) and v == 0:
        return None
    if isinstance(v, np.ndarray):
        return v.tolist()
    if hasattr(v, 'tolist') and callable(v.tolist):
        return v.tolist()
    return v
```

### Part 2: Type Checking (osc_calibrate_filter.py)

Added explicit type checking before attempting to use calibration data:

```python
# Check if calibration data exists and is valid (list/array, not scalar like 0)
has_valid_calib = (
    self.config.calib_evecs is not None and 
    self.config.calib_axes is not None and
    self.config.calib_XOFF is not None and
    # Ensure evecs and axes are lists/arrays, not scalars
    isinstance(self.config.calib_evecs, (list, tuple)) and
    isinstance(self.config.calib_axes, (list, tuple))
)
```

## Behavior After Fix

| Config Value | Validator Output | Application Behavior |
|--------------|------------------|----------------------|
| `"calib_axes": 0` (int) | Converted to `None` | Treated as uncalibrated ✅ |
| `"calib_axes": [15.5, 12.3]` | Kept as is | Valid calibration ✅ |
| `"calib_axes": null` | Kept as `None` | Treated as uncalibrated ✅ |

## Testing

### Unit Test

Created `tests/test_invalid_data_types.py` to verify:
- Integer 0 values are converted to None
- Valid array values still work
- None values work correctly
- Config loading doesn't crash

### Real-World Test

Tested with the exact JSON from the user's report:
- ✅ Config loads successfully
- ✅ Integer 0 → None conversion works
- ✅ Application starts without errors
- ✅ User can recalibrate normally

## User Impact

### Before Fix
```
User has corrupted config → Application crashes on startup → Can't use application
```

### After Fix
```
User has corrupted config → Values auto-fixed to None → Application starts → User sees "Please Calibrate" → User can recalibrate
```

## Prevention

This fix prevents the crash but also addresses the root cause:
1. **Validator** converts invalid data during load
2. **Type checking** prevents using invalid data
3. **Multiple validation layers** in calibration_elipse.py
4. **Graceful degradation** instead of crashes

## Commit

Fixed in commit: `1f5c562`
