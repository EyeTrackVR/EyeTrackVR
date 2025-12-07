# Calibration Bug Fix Documentation

## Problem Description

When users clicked "Stop Calibration" without first clicking "Start Calibration", the software would save empty/zero calibration data to the `eyetrack_settings.json` file. This would overwrite any previously valid calibration data with zeros, causing the software to crash with a `ValueError` during matrix operations (matmul) when trying to normalize eye positions.

## Root Cause

The bug occurred in the calibration flow:

1. **camera_widget.py (line 469)**: When "Stop Calibration" is clicked, it sets `calibration_frame_counter = 0`
2. **osc_calibrate_filter.py (line 198-203)**: When `calibration_frame_counter == 0`, it calls `fit_ellipse()` and saves the result
3. **calibration_elipse.py (line 37-42)**: When `fit_ellipse()` is called with no samples (< 2), it returns `(0, 0)` instead of valid calibration data
4. These zeros were then saved to the config file, overwriting valid calibration data
5. On next run, `normalize()` would try to perform matrix operations with zero matrices, causing a crash

## Solution

The fix implements three layers of protection, plus a fix for "Recenter Eyes" functionality:

### 1. Prevent Saving Invalid Calibration Data (osc_calibrate_filter.py)

**Location**: `EyeTrackApp/osc_calibrate_filter.py`, lines 202-220

**Change**: Separate handling of offset (XOFF/YOFF) and ellipse calibration (evecs/axes):

```python
if self.calibration_frame_counter == 0:
    self.calibration_frame_counter = None
    # Always save offset (XOFF/YOFF) for recenter functionality
    self.config.calib_XOFF = cx
    self.config.calib_YOFF = cy
    
    # Only save ellipse calibration data if samples were actually collected
    evecs, axes = self.cal.fit_ellipse()
    # Check if fit was successful (returns (0, 0) on failure)
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        # Valid calibration data - save it
        self.config.calib_evecs, self.config.calib_axes = evecs, axes
        self.baseconfig.save()
        PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
    else:
        # No samples collected - only save the offset (for Recenter Eyes)
        # Don't overwrite existing ellipse calibration
        print("\033[93m[WARN] Calibration stopped without collecting samples. Ellipse calibration preserved, offset updated.\033[0m")
        self.baseconfig.save()  # Still save to persist the offset changes
```

**Effect**: 
- When "Stop Calibration" is clicked without "Start Calibration", the ellipse calibration is preserved while the offset is still updated
- "Recenter Eyes" functionality now works correctly - it updates the offset without affecting ellipse calibration
- Normal calibration (with samples) saves both offset and ellipse data

### 2. Validate Loaded Calibration Data (calibration_elipse.py - init_from_save)

**Location**: `EyeTrackApp/utils/calibration_elipse.py`, lines 32-64

**Change**: Added comprehensive validation when loading saved calibration data:

```python
def init_from_save(self, evecs, axes):
    """Initialize calibration from saved data with validation"""
    try:
        evecs_array = np.asarray(evecs, dtype=float)
        axes_array = np.asarray(axes, dtype=float)
        
        # Validate evecs shape
        if evecs_array.shape != (2, 2):
            print(f"\033[91m[ERROR] Invalid evecs shape in saved data: {evecs_array.shape}. Expected (2, 2).\033[0m")
            self.fitted = False
            return False
        
        # Validate axes shape
        if axes_array.shape != (2,):
            print(f"\033[91m[ERROR] Invalid axes shape in saved data: {axes_array.shape}. Expected (2,).\033[0m")
            self.fitted = False
            return False
        
        # Check for zero or invalid values
        if np.all(axes_array == 0) or np.any(np.isnan(axes_array)) or np.any(np.isnan(evecs_array)):
            print("\033[91m[ERROR] Saved calibration data contains zero or NaN values.\033[0m")
            self.fitted = False
            return False
        
        self.evecs = evecs_array
        self.axes = axes_array
        self.fitted = True
        return True
        
    except (ValueError, TypeError) as e:
        print(f"\033[91m[ERROR] Failed to load calibration data: {e}\033[0m")
        self.fitted = False
        return False
```

**Effect**: If zero or invalid calibration data somehow gets saved to the config file, it will be detected and rejected on load rather than causing a crash.

### 3. Validate Before Matrix Operations (calibration_elipse.py - normalize)

**Location**: `EyeTrackApp/utils/calibration_elipse.py`, lines 131-177

**Change**: Added validation checks before performing matrix operations:

```python
def normalize(self, pupil_pos, target_pos=None, clip=True):
    if not self.fitted:
        return 0.0, 0.0

    # Validate calibration data before matrix operations
    if self.evecs is None or self.axes is None:
        print("\033[91m[ERROR] Calibration data (evecs/axes) is None. Please calibrate.\033[0m")
        return 0.0, 0.0
    
    # Check if evecs has valid shape
    if not isinstance(self.evecs, np.ndarray) or self.evecs.shape != (2, 2):
        print(f"\033[91m[ERROR] Invalid evecs shape: {self.evecs.shape if isinstance(self.evecs, np.ndarray) else type(self.evecs)}. Expected (2, 2). Please recalibrate.\033[0m")
        return 0.0, 0.0
    
    # Check if axes has valid shape and is not zero
    if not isinstance(self.axes, np.ndarray) or self.axes.shape != (2,):
        print(f"\033[91m[ERROR] Invalid axes shape: {self.axes.shape if isinstance(self.axes, np.ndarray) else type(self.axes)}. Expected (2,). Please recalibrate.\033[0m")
        return 0.0, 0.0
    
    # Check if axes contains valid non-zero values
    if np.all(self.axes == 0) or np.any(np.isnan(self.axes)):
        print("\033[91m[ERROR] Calibration axes are zero or invalid. Please recalibrate.\033[0m")
        return 0.0, 0.0
    
    # ... rest of normalize code with try/catch around matrix operations
```

**Effect**: Even if invalid data makes it through the other layers, the `normalize()` function will gracefully return `(0.0, 0.0)` with an error message instead of crashing with a ValueError.

## Testing

Two comprehensive test suites were created:

### Unit Tests (`tests/test_calibration_fix.py`)

Tests individual functions in isolation:
- `fit_ellipse()` behavior with 0, 1, and sufficient samples
- `init_from_save()` validation of valid, zero, and invalid data
- `normalize()` behavior with invalid calibration data

### Integration Tests (`tests/test_calibration_integration.py`)

Tests the full calibration workflow:
- Stop Calibration without Start Calibration (preserves old data)
- Stop Calibration with Start Calibration (saves new data)
- Loading corrupted data from config file
- Handling of corrupted data during normalize

All tests pass successfully.

## User-Visible Changes

1. **Before**: Clicking "Stop Calibration" without "Start Calibration" would zero out saved calibration data, causing crashes
2. **After**: Clicking "Stop Calibration" without "Start Calibration" displays a warning message and preserves existing calibration data

Warning message shown to user:
```
[WARN] Calibration stopped without collecting samples. Previous calibration data preserved.
```

Error messages for invalid calibration data:
```
[ERROR] Saved calibration data contains zero or NaN values.
[ERROR] Invalid evecs shape in saved data: (x, y). Expected (2, 2).
[ERROR] Invalid axes shape in saved data: (x,). Expected (2,).
[ERROR] Calibration axes are zero or invalid. Please recalibrate.
```

## Files Modified

1. `EyeTrackApp/osc_calibrate_filter.py` - Added validation before saving calibration data
2. `EyeTrackApp/utils/calibration_elipse.py` - Added validation in `init_from_save()` and `normalize()`
3. `tests/test_calibration_fix.py` - New unit tests
4. `tests/test_calibration_integration.py` - New integration tests

## Backward Compatibility

The changes are fully backward compatible:
- Valid calibration data continues to work as before
- Invalid/zero calibration data is now rejected gracefully instead of causing crashes
- No changes to the config file format or API

## Future Improvements

Potential enhancements that could be made in the future:
1. Add a UI indicator showing when calibration is in progress
2. Disable "Stop Calibration" button when calibration is not active
3. Add a confirmation dialog when stopping calibration early
4. Display the number of samples collected during calibration
