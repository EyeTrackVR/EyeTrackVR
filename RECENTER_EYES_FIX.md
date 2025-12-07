# Recenter Eyes Fix

## Issue Reported by @m-RNA

After the initial fix for the calibration bug, a new issue was discovered: clicking "Recenter Eyes" (without prior calibration) would not save the offset values.

## Root Cause

The original fix prevented ALL saves when `calibration_frame_counter == 0` and there were no calibration samples. However, the "Recenter Eyes" functionality also uses `calibration_frame_counter = 0` to trigger a save of the offset values (calib_XOFF, calib_YOFF).

### The Flow

1. User clicks "Recenter Eyes"
2. `gui_recenter_eyes` is set to True
3. In `cal_osc()`, when `gui_recenter_eyes == True` and `ts == 0`, it calls `center_overlay_calibrate()` 
4. `center_overlay_calibrate()` sets `calibration_frame_counter = 0`
5. On the next call to `cal_osc()`, `calibration_frame_counter == 0` triggers the save logic
6. The original fix saw no samples and prevented the save entirely

## Solution

Modified the logic in `osc_calibrate_filter.py` to distinguish between:
- **Offset data** (calib_XOFF, calib_YOFF) - always save when `calibration_frame_counter == 0`
- **Ellipse calibration** (calib_evecs, calib_axes) - only save if samples were collected

### Code Changes

```python
if self.calibration_frame_counter == 0:
    self.calibration_frame_counter = None
    # Always save offset (XOFF/YOFF) for recenter functionality
    self.config.calib_XOFF = cx
    self.config.calib_YOFF = cy
    
    # Only save ellipse calibration data if samples were actually collected
    evecs, axes = self.cal.fit_ellipse()
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        # Valid calibration data - save it
        self.config.calib_evecs, self.config.calib_axes = evecs, axes
        self.baseconfig.save()
        PlaySound(resource_path("Audio/completed.wav"), SND_FILENAME | SND_ASYNC)
    else:
        # No samples collected - only save the offset (for Recenter Eyes)
        print("\033[93m[WARN] Calibration stopped without collecting samples. Ellipse calibration preserved, offset updated.\033[0m")
        self.baseconfig.save()  # Still save to persist the offset changes
```

## Behavior After Fix

| Scenario | Offset (XOFF/YOFF) | Ellipse (evecs/axes) | Config Saved? |
|----------|-------------------|---------------------|---------------|
| **Recenter Eyes** (no calibration) | Updated ✅ | Preserved ✅ | Yes ✅ |
| **Stop Calibration** (no samples) | Updated ✅ | Preserved ✅ | Yes ✅ |
| **Normal Calibration** (with samples) | Updated ✅ | Updated ✅ | Yes ✅ |

## Testing

Added new test in `tests/test_recenter_eyes_fix.py`:
- Verifies offset is saved without samples
- Verifies ellipse calibration is preserved
- Verifies normal calibration still works

All tests pass:
- ✅ Original 13 tests still pass
- ✅ New Recenter Eyes test passes

## Commit

Fixed in commit: `a262e09`
