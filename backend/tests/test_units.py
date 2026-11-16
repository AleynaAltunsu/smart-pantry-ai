from app.cv.detector import _interpret_class
from app.forecasting import MIN_DAYS_FOR_RATE, quantity_to_value


def test_generic_yolo_class_is_never_prefilled():
    food, label, cat, kind = _interpret_class("plastic bottle", 0.95)
    assert food is None and kind == "generic" and label == "şişe"


def test_specific_class_prefilled_only_when_confident():
    assert _interpret_class("tomato", 0.6)[0] == "domates"
    food, _, _, kind = _interpret_class("tomato", 0.1)
    assert food is None and kind == "maybe"


def test_quantity_values():
    assert quantity_to_value("1") == 1
    assert quantity_to_value("less_half") < 1
    assert MIN_DAYS_FOR_RATE == 0.5
