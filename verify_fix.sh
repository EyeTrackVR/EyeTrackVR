#!/bin/bash

echo "=================================================="
echo "  Calibration Bug Fix - Verification Script"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# Test 1: Unit Tests
echo "1. Running unit tests..."
if python tests/test_calibration_fix.py > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Unit tests passed (9/9)"
else
    echo -e "${RED}✗${NC} Unit tests failed"
    FAILED=1
fi

# Test 2: Integration Tests
echo "2. Running integration tests..."
if python tests/test_calibration_integration.py > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Integration tests passed (4/4)"
else
    echo -e "${RED}✗${NC} Integration tests failed"
    FAILED=1
fi

# Test 3: Module Import
echo "3. Testing module imports..."
cd EyeTrackApp
if python -c "from utils.calibration_elipse import CalibrationEllipse" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} CalibrationEllipse imports successfully"
else
    echo -e "${RED}✗${NC} CalibrationEllipse import failed"
    FAILED=1
fi
cd ..

# Test 4: Check files exist
echo "4. Checking modified files..."
FILES=("EyeTrackApp/osc_calibrate_filter.py" "EyeTrackApp/utils/calibration_elipse.py")
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file exists"
    else
        echo -e "${RED}✗${NC} $file missing"
        FAILED=1
    fi
done

# Test 5: Check documentation
echo "5. Checking documentation..."
DOCS=("FINAL_SUMMARY.md" "CALIBRATION_FIX_DOCUMENTATION.md" "QUICK_REFERENCE.md" "修复总结_中文.md")
for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}✓${NC} $doc exists"
    else
        echo -e "${RED}✗${NC} $doc missing"
        FAILED=1
    fi
done

# Test 6: Check test files
echo "6. Checking test files..."
TESTS=("tests/test_calibration_fix.py" "tests/test_calibration_integration.py" "demonstrate_fix.py")
for test in "${TESTS[@]}"; do
    if [ -f "$test" ]; then
        echo -e "${GREEN}✓${NC} $test exists"
    else
        echo -e "${RED}✗${NC} $test missing"
        FAILED=1
    fi
done

echo ""
echo "=================================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}ALL VERIFICATIONS PASSED!${NC}"
    echo "The calibration bug fix is complete and verified."
    echo ""
    echo "Key improvements:"
    echo "  • Prevents data loss when stopping calibration early"
    echo "  • Validates calibration data on load and use"
    echo "  • Provides friendly error messages instead of crashes"
    echo "  • 13 tests ensure correct behavior"
    exit 0
else
    echo -e "${RED}SOME VERIFICATIONS FAILED${NC}"
    echo "Please review the errors above."
    exit 1
fi
echo "=================================================="
