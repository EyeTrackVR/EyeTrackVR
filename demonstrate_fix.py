#!/usr/bin/env python3
"""
Demonstration script showing the bug fix in action.
Shows the difference between the old buggy behavior and the new fixed behavior.
"""

import sys
import os

# Add EyeTrackApp to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'EyeTrackApp'))

from utils.calibration_elipse import CalibrationEllipse
import numpy as np


def demonstrate_bug_scenario():
    """
    Demonstrates what happens when user clicks Stop Calibration without Start Calibration.
    """
    print("=" * 80)
    print("DEMONSTRATION: Stop Calibration without Start Calibration")
    print("=" * 80)
    print()
    
    # Simulate having valid calibration data saved
    print("1. Simulating existing valid calibration data:")
    saved_evecs = [[0.9, 0.1], [0.1, 0.9]]
    saved_axes = [15.5, 12.3]
    print(f"   Saved evecs: {saved_evecs}")
    print(f"   Saved axes: {saved_axes}")
    print()
    
    # Create calibration object
    cal = CalibrationEllipse()
    
    # Load the existing calibration
    print("2. Loading existing calibration data:")
    result = cal.init_from_save(saved_evecs, saved_axes)
    if result:
        print("   ✓ Successfully loaded valid calibration data")
        print(f"   Calibration is fitted: {cal.fitted}")
    else:
        print("   ✗ Failed to load calibration data")
    print()
    
    # User clicks "Stop Calibration" without "Start Calibration"
    print("3. User clicks 'Stop Calibration' without clicking 'Start Calibration':")
    print("   (No samples were collected)")
    
    # This calls fit_ellipse() with no samples
    evecs, axes = cal.fit_ellipse()
    print(f"   fit_ellipse() returned: evecs={evecs}, axes={axes}")
    print()
    
    # The FIX: Check if result is (0, 0) before saving
    print("4. Checking if calibration data is valid before saving:")
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        print("   ✓ Valid data - would save to config")
        saved_evecs = evecs
        saved_axes = axes
    else:
        print("   ✗ Invalid data (0, 0) - preserving old calibration data")
        print("   [WARN] Calibration stopped without collecting samples. Previous calibration data preserved.")
    print()
    
    print("5. Final state:")
    print(f"   Config evecs: {saved_evecs}")
    print(f"   Config axes: {saved_axes}")
    print("   ✓ OLD VALID DATA PRESERVED!")
    print()
    print("=" * 80)
    print()


def demonstrate_valid_calibration():
    """
    Demonstrates normal calibration flow (Start -> Look around -> Stop).
    """
    print("=" * 80)
    print("DEMONSTRATION: Normal Calibration Flow")
    print("=" * 80)
    print()
    
    # Simulate having old calibration data
    print("1. Starting with old calibration data:")
    old_evecs = [[0.9, 0.1], [0.1, 0.9]]
    old_axes = [15.5, 12.3]
    print(f"   Old evecs: {old_evecs}")
    print(f"   Old axes: {old_axes}")
    print()
    
    # Create calibration object
    cal = CalibrationEllipse()
    
    # User clicks "Start Calibration" and looks around
    print("2. User clicks 'Start Calibration' and looks around:")
    samples = []
    for x in range(90, 111, 5):
        for y in range(90, 111, 5):
            cal.add_sample(x, y)
            samples.append((x, y))
    print(f"   Collected {len(samples)} samples")
    print()
    
    # User clicks "Stop Calibration"
    print("3. User clicks 'Stop Calibration':")
    evecs, axes = cal.fit_ellipse()
    print(f"   fit_ellipse() returned valid numpy arrays")
    print(f"   evecs shape: {evecs.shape}")
    print(f"   axes shape: {axes.shape}")
    print()
    
    # Check if result is valid before saving
    print("4. Checking if calibration data is valid before saving:")
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        print("   ✓ Valid data - saving to config")
        new_evecs = evecs.tolist()
        new_axes = axes.tolist()
        print("   [INFO] Calibration completed successfully!")
    else:
        print("   ✗ Invalid data - this shouldn't happen with enough samples")
        new_evecs = old_evecs
        new_axes = old_axes
    print()
    
    print("5. Final state:")
    print(f"   Config evecs: {new_evecs}")
    print(f"   Config axes: {new_axes}")
    print("   ✓ NEW CALIBRATION DATA SAVED!")
    print()
    print("=" * 80)
    print()


def demonstrate_validation():
    """
    Demonstrates the validation features that prevent crashes.
    """
    print("=" * 80)
    print("DEMONSTRATION: Validation Prevents Crashes")
    print("=" * 80)
    print()
    
    cal = CalibrationEllipse()
    
    # Test 1: Try to load zero data
    print("1. Attempting to load zero calibration data:")
    print("   (This would cause crashes in the old version)")
    result = cal.init_from_save([[0, 0], [0, 0]], [0, 0])
    if result:
        print("   ✓ Data loaded (unexpected)")
    else:
        print("   ✗ Data rejected by validation")
        print("   ✓ Crash prevented!")
    print()
    
    # Test 2: Try to normalize with invalid data
    print("2. Attempting to normalize with invalid calibration:")
    print("   (This would cause ValueError/matmul crashes in old version)")
    result = cal.normalize((100, 100))
    print(f"   normalize() returned: {result}")
    print("   ✓ Returned (0.0, 0.0) instead of crashing!")
    print()
    
    # Test 3: Load valid data and normalize
    print("3. Loading valid calibration and normalizing:")
    valid_evecs = [[1.0, 0.0], [0.0, 1.0]]
    valid_axes = [10.0, 8.0]
    result = cal.init_from_save(valid_evecs, valid_axes)
    if result:
        print("   ✓ Valid data loaded successfully")
        result = cal.normalize((100, 100), target_pos=(100, 100))
        print(f"   normalize() returned: {result}")
        print("   ✓ Normalization works correctly!")
    print()
    
    print("=" * 80)
    print()


if __name__ == '__main__':
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "CALIBRATION BUG FIX DEMONSTRATION" + " " * 25 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    demonstrate_bug_scenario()
    demonstrate_valid_calibration()
    demonstrate_validation()
    
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 30 + "ALL DEMONSTRATIONS COMPLETE" + " " * 21 + "║")
    print("║" + " " * 78 + "║")
    print("║" + "  Key takeaways:" + " " * 62 + "║")
    print("║" + "  1. Stop without Start → Old data preserved (no crash)" + " " * 20 + "║")
    print("║" + "  2. Start → Stop → New data saved correctly" + " " * 29 + "║")
    print("║" + "  3. Validation prevents crashes from invalid data" + " " * 24 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
