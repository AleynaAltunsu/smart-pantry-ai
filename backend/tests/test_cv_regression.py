from pathlib import Path

import pytest

from app.cv.detector import detect_regions

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("name,minimum", [("fake_fridge.jpg", 3), ("fake_fridge2.jpg", 5), ("corner_test.jpg", 2)])
def test_classical_detector_min_regions(name, minimum):
    result = detect_regions((DATA / name).read_bytes())
    assert len(result["regions"]) >= minimum
