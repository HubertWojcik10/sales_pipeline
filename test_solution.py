import pandas as pd
import pytest
from solution import add_virtual_column


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})


@pytest.mark.parametrize(
    "role, expected",
    [
        ("a + b * c", [16, 26]),
        ("a - b - c", [-7, -8]),
        ("a*b", [3, 8]),
    ],
)
def test_valid_role(df: pd.DataFrame, role: str, expected: list[int]) -> None:
    result = add_virtual_column(df, role, "x")
    assert result["x"].tolist() == expected
    assert list(result.columns) == ["a", "b", "c", "x"]


@pytest.mark.parametrize("role", ["", "a +", "a ++ b", "a / b", "a * 2", "-a", "a + missing"])
def test_invalid_role_returns_empty(df: pd.DataFrame, role: str) -> None:
    assert add_virtual_column(df, role, "x").empty


@pytest.mark.parametrize("new_column", ["", "x1", "x-y", "x y"])
def test_invalid_new_column_returns_empty(df: pd.DataFrame, new_column: str) -> None:
    assert add_virtual_column(df, "a + b", new_column).empty


def test_input_is_not_mutated(df: pd.DataFrame) -> None:
    add_virtual_column(df, "a + b", "x")
    assert list(df.columns) == ["a", "b", "c"]


@pytest.mark.parametrize("keyword", ["True", "and", "not"])
def test_column_named_like_python_keyword(df: pd.DataFrame, keyword: str) -> None:
    """ A column must be read as a column, not as a literal or operator. """
    df_keyword = df.assign(**{keyword: [10, 10]})
    result = add_virtual_column(df_keyword, f"a + {keyword}", "x")
    assert result["x"].tolist() == [11, 12]


def test_unused_invalid_column_is_ignored(df: pd.DataFrame) -> None:
    """ Only labels used in the role are validated. """
    result = add_virtual_column(df.assign(col1=[0, 0]), "a + b", "x")
    assert result["x"].tolist() == [4, 6]
