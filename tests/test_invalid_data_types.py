#!/usr/bin/env python3
"""
Test for handling invalid calibration data types (e.g., integer 0 instead of arrays).
This tests the scenario reported where calib_axes and calib_evecs are set to 0 (integer).
"""

import sys
import os

# Add EyeTrackApp to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'EyeTrackApp'))

from config import EyeTrackCameraConfig
from utils.calibration_elipse import CalibrationEllipse


def test_config_with_integer_zeros():
    """
    Test that config with calib_axes=0 and calib_evecs=0 (integers) doesn't crash.
    This is the scenario from the user's eyetrack_settings.json file.
    """
    print("=" * 80)
    print("TEST: Config with integer zeros (calib_axes=0, calib_evecs=0)")
    print("=" * 80)
    
    # Create config with integer 0 values (like in the user's file)
    # The validator should convert these to None
    try:
        config = EyeTrackCameraConfig(
            calib_axes=0,  # Integer 0, should be converted to None
            calib_evecs=0,  # Integer 0, should be converted to None
            calib_XOFF=74.36,
            calib_YOFF=36.55
        )
        print("\n1. Config created successfully")
        print(f"   calib_axes type: {type(config.calib_axes)}, value: {config.calib_axes}")
        print(f"   calib_evecs type: {type(config.calib_evecs)}, value: {config.calib_evecs}")
        print(f"   calib_XOFF: {config.calib_XOFF}")
        print(f"   calib_YOFF: {config.calib_YOFF}")
        
        # After validation, integer 0 should be converted to None
        assert config.calib_axes is None, "calib_axes=0 should be converted to None"
        assert config.calib_evecs is None, "calib_evecs=0 should be converted to None"
        print("   ✓ Integer 0 values correctly converted to None")
        
    except Exception as e:
        print(f"\n✗ Failed to create config: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test type checking (should now be None, so type check not needed)
    print("\n2. Testing type checks:")
    if config.calib_evecs is None or config.calib_axes is None:
        print(f"   Values are None, no type check needed")
        print("   ✓ None values handled correctly")
    else:
        print(f"   ✗ Values should be None but aren't")
        return False
    
    print("\n✓ TEST PASSED: Integer zeros converted to None and handled gracefully!")
    print("=" * 80)
    return True


def test_config_with_valid_arrays():
    """
    Test that valid array data still works correctly.
    """
    print("\n" + "=" * 80)
    print("TEST: Config with valid array data")
    print("=" * 80)
    
    # Create config with valid array values
    config = EyeTrackCameraConfig(
        calib_axes=[15.5, 12.3],
        calib_evecs=[[0.9, 0.1], [0.1, 0.9]],
        calib_XOFF=100.0,
        calib_YOFF=100.0
    )
    
    print("\n1. Config created successfully")
    print(f"   calib_axes type: {type(config.calib_axes)}")
    print(f"   calib_evecs type: {type(config.calib_evecs)}")
    
    # Test type checking
    print("\n2. Testing type checks:")
    is_list_or_tuple_evecs = isinstance(config.calib_evecs, (list, tuple))
    is_list_or_tuple_axes = isinstance(config.calib_axes, (list, tuple))
    print(f"   calib_evecs is list/tuple: {is_list_or_tuple_evecs}")
    print(f"   calib_axes is list/tuple: {is_list_or_tuple_axes}")
    
    assert is_list_or_tuple_evecs, "calib_evecs should be recognized as list/tuple"
    assert is_list_or_tuple_axes, "calib_axes should be recognized as list/tuple"
    print("   ✓ Type checks correctly identify valid lists")
    
    # Test that init_from_save works
    print("\n3. Testing init_from_save with valid values:")
    cal = CalibrationEllipse()
    result = cal.init_from_save(config.calib_evecs, config.calib_axes)
    
    print(f"   init_from_save returned: {result}")
    print(f"   Calibration fitted: {cal.fitted}")
    
    assert result == True, "init_from_save should return True for valid data"
    assert cal.fitted == True, "Calibration should be fitted"
    print("   ✓ init_from_save accepted valid data")
    
    print("\n✓ TEST PASSED: Valid arrays work correctly!")
    print("=" * 80)
    return True


def test_config_with_none_values():
    """
    Test that None values are handled correctly.
    """
    print("\n" + "=" * 80)
    print("TEST: Config with None values")
    print("=" * 80)
    
    # Create config with None values
    config = EyeTrackCameraConfig(
        calib_axes=None,
        calib_evecs=None,
        calib_XOFF=None,
        calib_YOFF=None
    )
    
    print("\n1. Config created successfully")
    print(f"   calib_axes: {config.calib_axes}")
    print(f"   calib_evecs: {config.calib_evecs}")
    
    # Test type checking
    print("\n2. Testing type checks:")
    if config.calib_evecs is not None and config.calib_axes is not None:
        is_list_or_tuple_evecs = isinstance(config.calib_evecs, (list, tuple))
        is_list_or_tuple_axes = isinstance(config.calib_axes, (list, tuple))
        print(f"   Would check types, but values are None")
    else:
        print(f"   Correctly identified as None values")
        print("   ✓ None values handled correctly in type check")
    
    print("\n✓ TEST PASSED: None values handled correctly!")
    print("=" * 80)
    return True


if __name__ == '__main__':
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 25 + "INVALID DATA TYPE TESTS" + " " * 29 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    all_pass = True
    
    all_pass &= test_config_with_integer_zeros()
    all_pass &= test_config_with_valid_arrays()
    all_pass &= test_config_with_none_values()
    
    print("\n" + "╔" + "=" * 78 + "╗")
    if all_pass:
        print("║" + " " * 30 + "ALL TESTS PASSED ✓" + " " * 28 + "║")
    else:
        print("║" + " " * 30 + "SOME TESTS FAILED ✗" + " " * 27 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
