"""Tests for the random animal name generator."""

from pop_quiz.animals import random_animal_name


def test_returns_non_empty_string() -> None:
    """random_animal_name should return a non-empty string."""
    name = random_animal_name()
    assert isinstance(name, str)
    assert len(name) > 0


def test_contains_separator() -> None:
    """The returned name should join an adjective and an animal with a space."""
    name = random_animal_name()
    assert " " in name


def test_multiple_calls_return_strings() -> None:
    """Several calls should each return a string."""
    for _ in range(10):
        assert isinstance(random_animal_name(), str)
