import pytest

from app.tools.basic import evaluate_expression


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("(25 + 17) * 3", 126),
        ("sqrt(81)", 9),
        ("2 ** 10", 1024),
    ],
)
def test_evaluate_expression(expression: str, expected: int | float) -> None:
    assert evaluate_expression(expression) == expected


def test_evaluate_expression_rejects_code_execution() -> None:
    with pytest.raises(ValueError):
        evaluate_expression("__import__('os').system('whoami')")

