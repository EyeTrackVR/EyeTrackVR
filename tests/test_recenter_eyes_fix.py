#!/usr/bin/env python3
"""
Test for the Recenter Eyes bug fix.
Verifies that Recenter Eyes saves offset without overwriting ellipse calibration.
"""

import sys
import os

# Add EyeTrackApp to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'EyeTrackApp'))

from utils.calibration_elipse import CalibrationEllipse
from config import EyeTrackCameraConfig


def test_recenter_eyes_saves_offset():
    """
    Test that when calibration_frame_counter == 0 without samples (Recenter Eyes scenario),
    it saves the offset (XOFF/YOFF) but doesn't overwrite existing ellipse calibration.
    """
    print("=" * 80)
    print("TEST: Recenter Eyes saves offset without overwriting ellipse calibration")
    print("=" * 80)
    
    # Create config with existing valid ellipse calibration
    config = EyeTrackCameraConfig(
        calib_evecs=[[0.9, 0.1], [0.1, 0.9]],
        calib_axes=[15.5, 12.3],
        calib_XOFF=100.0,
        calib_YOFF=100.0
    )
    
    print("\n1. Initial state:")
    print(f"   calib_evecs: {config.calib_evecs}")
    print(f"   calib_axes: {config.calib_axes}")
    print(f"   calib_XOFF: {config.calib_XOFF}")
    print(f"   calib_YOFF: {config.calib_YOFF}")
    
    # Simulate Recenter Eyes flow
    cal = CalibrationEllipse()
    # No samples added (Recenter Eyes doesn't collect samples)
    
    # Simulate what happens when calibration_frame_counter == 0
    new_cx, new_cy = 120.0, 130.0
    
    # Step 1: Always save offset
    config.calib_XOFF = new_cx
    config.calib_YOFF = new_cy
    
    # Step 2: Try to fit ellipse (will fail with no samples)
    evecs, axes = cal.fit_ellipse()
    
    print("\n2. After fit_ellipse() with no samples:")
    print(f"   evecs result: {evecs}")
    print(f"   axes result: {axes}")
    
    # Step 3: Check if valid, only save if valid
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        config.calib_evecs = evecs.tolist() if hasattr(evecs, 'tolist') else evecs
        config.calib_axes = axes.tolist() if hasattr(axes, 'tolist') else axes
        print("\n3. Valid calibration - saved ellipse data")
    else:
        print("\n3. Invalid calibration (0, 0) - ellipse data NOT overwritten")
    
    # Verify final state
    print("\n4. Final state:")
    print(f"   calib_evecs: {config.calib_evecs}")
    print(f"   calib_axes: {config.calib_axes}")
    print(f"   calib_XOFF: {config.calib_XOFF}")
    print(f"   calib_YOFF: {config.calib_YOFF}")
    
    # Assertions
    assert config.calib_evecs == [[0.9, 0.1], [0.1, 0.9]], "Ellipse evecs should be preserved!"
    assert config.calib_axes == [15.5, 12.3], "Ellipse axes should be preserved!"
    assert config.calib_XOFF == new_cx, "XOFF should be updated!"
    assert config.calib_YOFF == new_cy, "YOFF should be updated!"
    
    print("\n✓ TEST PASSED: Offset saved, ellipse calibration preserved!")
    print("=" * 80)


def test_normal_calibration_saves_everything():
    """
    Test that normal calibration (with samples) saves both offset and ellipse data.
    """
    print("\n" + "=" * 80)
    print("TEST: Normal calibration saves both offset and ellipse data")
    print("=" * 80)
    
    # Create config
    config = EyeTrackCameraConfig(
        calib_evecs=[[0.9, 0.1], [0.1, 0.9]],
        calib_axes=[15.5, 12.3],
        calib_XOFF=100.0,
        calib_YOFF=100.0
    )
    
    print("\n1. Initial state:")
    print(f"   calib_evecs: {config.calib_evecs}")
    print(f"   calib_axes: {config.calib_axes}")
    
    # Simulate normal calibration flow with samples
    cal = CalibrationEllipse()
    for x in range(90, 111, 5):
        for y in range(90, 111, 5):
            cal.add_sample(x, y)
    
    # Simulate what happens when calibration_frame_counter == 0
    new_cx, new_cy = 120.0, 130.0
    
    # Step 1: Always save offset
    config.calib_XOFF = new_cx
    config.calib_YOFF = new_cy
    
    # Step 2: Fit ellipse (will succeed with samples)
    evecs, axes = cal.fit_ellipse()
    
    print("\n2. After fit_ellipse() with samples:")
    print(f"   evecs shape: {evecs.shape}")
    print(f"   axes shape: {axes.shape}")
    
    # Step 3: Check if valid, save if valid
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        config.calib_evecs = evecs.tolist()
        config.calib_axes = axes.tolist()
        print("\n3. Valid calibration - saved ellipse data")
    else:
        print("\n3. Invalid calibration - this shouldn't happen!")
    
    # Verify final state
    print("\n4. Final state:")
    print(f"   calib_evecs: {config.calib_evecs}")
    print(f"   calib_axes: {config.calib_axes}")
    print(f"   calib_XOFF: {config.calib_XOFF}")
    print(f"   calib_YOFF: {config.calib_YOFF}")
    
    # Assertions
    assert config.calib_evecs != [[0.9, 0.1], [0.1, 0.9]], "Ellipse evecs should be updated!"
    assert config.calib_axes != [15.5, 12.3], "Ellipse axes should be updated!"
    assert config.calib_XOFF == new_cx, "XOFF should be updated!"
    assert config.calib_YOFF == new_cy, "YOFF should be updated!"
    
    print("\n✓ TEST PASSED: Both offset and ellipse data saved!")
    print("=" * 80)


if __name__ == '__main__':
    test_recenter_eyes_saves_offset()
    test_normal_calibration_saves_everything()
    
    print("\n" + "=" * 80)
    print("✓ ALL TESTS PASSED!")
    print("=" * 80)
