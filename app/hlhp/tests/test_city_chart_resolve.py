"""Tests for city-chart locality → board mapping."""

from app.hlhp.services.city_chart_service import resolve_chart_city


def test_baner_maps_to_pune():
    city, on_board = resolve_chart_city("Baner")
    assert city == "Pune"
    assert on_board is True


def test_baner_pune_maharashtra_maps_to_pune():
    city, on_board = resolve_chart_city("Baner, Pune, Maharashtra")
    assert city == "Pune"
    assert on_board is True


def test_board_city_passthrough():
    city, on_board = resolve_chart_city("Mumbai")
    assert city == "Mumbai"
    assert on_board is True


def test_outside_board_becomes_twelfth():
    city, on_board = resolve_chart_city("Nagpur")
    assert city == "Nagpur"
    assert on_board is False
