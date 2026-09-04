import pytest
from skills.billing import _calculate_gst

def test_gst_calculation_zero_percent():
    res = _calculate_gst(100.0, 0.0)
    assert res["subtotal"] == 100.0
    assert res["cgst"] == 0.0
    assert res["sgst"] == 0.0
    assert res["total_tax"] == 0.0
    assert res["line_total"] == 100.0

def test_gst_calculation_five_percent():
    res = _calculate_gst(200.0, 5.0)
    assert res["subtotal"] == 200.0
    assert res["cgst"] == 5.0
    assert res["sgst"] == 5.0
    assert res["total_tax"] == 10.0
    assert res["line_total"] == 210.0

def test_gst_calculation_twelve_percent():
    res = _calculate_gst(275.0, 12.0)
    assert res["subtotal"] == 275.0
    assert res["cgst"] == 16.5
    assert res["sgst"] == 16.5
    assert res["total_tax"] == 33.0
    assert res["line_total"] == 308.0

def test_gst_calculation_eighteen_percent():
    res = _calculate_gst(14.0, 18.0) # Maggi 70g
    assert res["subtotal"] == 14.0
    # 14 * 0.18 = 2.52 -> CGST = 1.26, SGST = 1.26
    assert res["cgst"] == 1.26
    assert res["sgst"] == 1.26
    assert res["total_tax"] == 2.52
    assert res["line_total"] == 16.52
