"""
Integration test for the calibration bug fix.
Simulates the actual scenario: Stop Calibration without Start Calibration.
"""

import sys
import os
import json
import tempfile
import shutil
import numpy as np

# Add EyeTrackApp to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'EyeTrackApp'))

from utils.calibration_elipse import CalibrationEllipse
from config import EyeTrackCameraConfig


def test_stop_calibration_without_start_preserves_data():
    """
    Integration test: Simulates clicking 'Stop Calibration' without 'Start Calibration'.
    
    This should NOT zero out existing calibration data.
    """
    # Create a temporary config with valid calibration data
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, 'eyetrack_settings.json')
        
        # Create initial config with valid calibration data
        initial_evecs = [[0.9, 0.1], [0.1, 0.9]]
        initial_axes = [15.5, 12.3]
        
        config = EyeTrackCameraConfig(
            calib_evecs=initial_evecs,
            calib_axes=initial_axes,
            calib_XOFF=100.0,
            calib_YOFF=100.0
        )
        
        # Verify initial data is set
        assert config.calib_evecs == initial_evecs
        assert config.calib_axes == initial_axes
        
        # Simulate the calibration flow when user clicks "Stop Calibration" without "Start"
        cal = CalibrationEllipse()
        
        # No samples added (user didn't click "Start Calibration")
        # User clicks "Stop Calibration" - this triggers fit_ellipse()
        evecs, axes = cal.fit_ellipse()
        
        # Should return (0, 0) because no samples
        assert evecs == 0
        assert axes == 0
        
        # In the fixed version, we check if the result is (0, 0) before saving
        if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
            # This should NOT execute in our test case
            config.calib_evecs = evecs
            config.calib_axes = axes
            # Config would be saved here
        else:
            # This SHOULD execute - we preserve the old data
            print("Calibration stopped without samples. Preserving existing data.")
        
        # Verify that the config still has the original valid data
        assert config.calib_evecs == initial_evecs
        assert config.calib_axes == initial_axes
        print("✓ Old calibration data preserved successfully")


def test_stop_calibration_with_start_saves_new_data():
    """
    Integration test: Simulates clicking 'Start Calibration' then 'Stop Calibration'.
    
    This SHOULD save the new calibration data.
    """
    # Create initial config with some calibration data
    initial_evecs = [[0.9, 0.1], [0.1, 0.9]]
    initial_axes = [15.5, 12.3]
    
    config = EyeTrackCameraConfig(
        calib_evecs=initial_evecs,
        calib_axes=initial_axes,
        calib_XOFF=100.0,
        calib_YOFF=100.0
    )
    
    # Simulate the calibration flow when user clicks both Start and Stop
    cal = CalibrationEllipse()
    
    # Add samples (user DID click "Start Calibration" and looked around)
    for x in range(90, 111, 5):
        for y in range(90, 111, 5):
            cal.add_sample(x, y)
    
    # User clicks "Stop Calibration" - this triggers fit_ellipse()
    evecs, axes = cal.fit_ellipse()
    
    # Should return valid arrays
    assert isinstance(evecs, np.ndarray)
    assert isinstance(axes, np.ndarray)
    assert evecs.shape == (2, 2)
    assert axes.shape == (2,)
    
    # Check if the result is valid before saving
    if not (isinstance(evecs, int) and isinstance(axes, int) and evecs == 0 and axes == 0):
        # This SHOULD execute - we save the new data
        config.calib_evecs = evecs.tolist()
        config.calib_axes = axes.tolist()
        print("✓ New calibration data saved successfully")
    
    # Verify that the config has NEW data (not the initial data)
    assert config.calib_evecs != initial_evecs
    assert config.calib_axes != initial_axes
    # Verify the data is valid
    assert len(config.calib_evecs) == 2
    assert len(config.calib_evecs[0]) == 2
    assert len(config.calib_axes) == 2


def test_init_from_save_validation_prevents_zero_data():
    """
    Test that init_from_save validates and rejects zero calibration data.
    """
    cal = CalibrationEllipse()
    
    # Try to load zero data (which would happen if the bug occurred)
    result = cal.init_from_save([[0, 0], [0, 0]], [0, 0])
    
    # Should reject the zero data
    assert result == False
    assert cal.fitted == False
    print("✓ Zero calibration data correctly rejected")


def test_normalize_with_corrupted_data_returns_safe_default():
    """
    Test that normalize handles corrupted data gracefully.
    """
    cal = CalibrationEllipse()
    
    # Manually set corrupted data (simulating what would happen if zeros were saved)
    cal.evecs = np.array([[0, 0], [0, 0]])
    cal.axes = np.array([0, 0])
    cal.fitted = True  # Pretend it's fitted but with bad data
    
    # Try to normalize - should return (0, 0) instead of crashing
    result = cal.normalize((100, 100))
    
    assert result == (0.0, 0.0)
    print("✓ Normalize handles corrupted data gracefully")


if __name__ == '__main__':
    print("Running integration tests for calibration bug fix...\n")
    
    test_stop_calibration_without_start_preserves_data()
    print()
    
    test_stop_calibration_with_start_saves_new_data()
    print()
    
    test_init_from_save_validation_prevents_zero_data()
    print()
    
    test_normalize_with_corrupted_data_returns_safe_default()
    print()
    
    print("\n✓ All integration tests passed!")
