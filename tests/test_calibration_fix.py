"""
Test for the calibration bug fix.
Tests that stopping calibration without starting it doesn't zero out saved calibration data.
"""

import sys
import os
import numpy as np

# Add EyeTrackApp to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'EyeTrackApp'))

from utils.calibration_elipse import CalibrationEllipse


def test_fit_ellipse_with_no_samples():
    """Test that fit_ellipse returns (0, 0) when no samples are added"""
    cal = CalibrationEllipse()
    evecs, axes = cal.fit_ellipse()
    
    # Should return (0, 0) when no samples
    assert evecs == 0
    assert axes == 0
    assert cal.fitted == False


def test_fit_ellipse_with_one_sample():
    """Test that fit_ellipse returns (0, 0) with only one sample"""
    cal = CalibrationEllipse()
    cal.add_sample(100, 100)
    evecs, axes = cal.fit_ellipse()
    
    # Should return (0, 0) when only one sample
    assert evecs == 0
    assert axes == 0
    assert cal.fitted == False


def test_fit_ellipse_with_sufficient_samples():
    """Test that fit_ellipse works correctly with enough samples"""
    cal = CalibrationEllipse()
    
    # Add multiple samples in different positions
    samples = [
        (100, 100), (110, 100), (100, 110), (110, 110),
        (90, 100), (100, 90), (90, 110), (110, 90),
        (95, 95), (105, 105), (95, 105), (105, 95)
    ]
    
    for x, y in samples:
        cal.add_sample(x, y)
    
    evecs, axes = cal.fit_ellipse()
    
    # Should return valid arrays
    assert isinstance(evecs, np.ndarray)
    assert isinstance(axes, np.ndarray)
    assert evecs.shape == (2, 2)
    assert axes.shape == (2,)
    assert cal.fitted == True


def test_init_from_save_with_valid_data():
    """Test init_from_save with valid calibration data"""
    cal = CalibrationEllipse()
    
    # Valid calibration data
    valid_evecs = [[1.0, 0.0], [0.0, 1.0]]
    valid_axes = [10.0, 8.0]
    
    result = cal.init_from_save(valid_evecs, valid_axes)
    
    assert result == True
    assert cal.fitted == True
    assert cal.evecs.shape == (2, 2)
    assert cal.axes.shape == (2,)


def test_init_from_save_with_zero_axes():
    """Test init_from_save rejects zero axes"""
    cal = CalibrationEllipse()
    
    # Invalid: zero axes
    zero_evecs = [[1.0, 0.0], [0.0, 1.0]]
    zero_axes = [0.0, 0.0]
    
    result = cal.init_from_save(zero_evecs, zero_axes)
    
    assert result == False
    assert cal.fitted == False


def test_init_from_save_with_invalid_shape():
    """Test init_from_save rejects invalid shapes"""
    cal = CalibrationEllipse()
    
    # Invalid: wrong shape
    invalid_evecs = [[1.0, 0.0]]  # Should be 2x2
    invalid_axes = [10.0, 8.0]
    
    result = cal.init_from_save(invalid_evecs, invalid_axes)
    
    assert result == False
    assert cal.fitted == False


def test_normalize_with_invalid_calibration():
    """Test normalize returns (0, 0) with invalid calibration"""
    cal = CalibrationEllipse()
    
    # Try to normalize without calibration
    result = cal.normalize((100, 100))
    
    assert result == (0.0, 0.0)


def test_normalize_with_zero_calibration():
    """Test normalize handles zero calibration data gracefully"""
    cal = CalibrationEllipse()
    
    # Try to load zero calibration data
    cal.init_from_save([[0, 0], [0, 0]], [0, 0])
    
    # normalize should return (0, 0) due to validation
    result = cal.normalize((100, 100))
    
    assert result == (0.0, 0.0)


def test_normalize_with_valid_calibration():
    """Test normalize works correctly with valid calibration"""
    cal = CalibrationEllipse()
    
    # Add samples and fit
    for x in range(90, 111, 5):
        for y in range(90, 111, 5):
            cal.add_sample(x, y)
    
    cal.fit_ellipse()
    
    # Should be able to normalize
    result = cal.normalize((100, 100))
    
    # Result should be valid floats, not (0, 0)
    assert isinstance(result[0], float)
    assert isinstance(result[1], float)
    # At center, should be close to (0, 0) but not exactly due to calibration
    assert abs(result[0]) < 1.0
    assert abs(result[1]) < 1.0


if __name__ == '__main__':
    # Run tests
    test_fit_ellipse_with_no_samples()
    print("✓ test_fit_ellipse_with_no_samples passed")
    
    test_fit_ellipse_with_one_sample()
    print("✓ test_fit_ellipse_with_one_sample passed")
    
    test_fit_ellipse_with_sufficient_samples()
    print("✓ test_fit_ellipse_with_sufficient_samples passed")
    
    test_init_from_save_with_valid_data()
    print("✓ test_init_from_save_with_valid_data passed")
    
    test_init_from_save_with_zero_axes()
    print("✓ test_init_from_save_with_zero_axes passed")
    
    test_init_from_save_with_invalid_shape()
    print("✓ test_init_from_save_with_invalid_shape passed")
    
    test_normalize_with_invalid_calibration()
    print("✓ test_normalize_with_invalid_calibration passed")
    
    test_normalize_with_zero_calibration()
    print("✓ test_normalize_with_zero_calibration passed")
    
    test_normalize_with_valid_calibration()
    print("✓ test_normalize_with_valid_calibration passed")
    
    print("\nAll tests passed! ✓")
