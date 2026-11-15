import logging
import numpy as np
import pandas as pd
import pytest
from pipeline import Pipeline


def test_rename_to_snake_case() -> None:
    raw = pd.DataFrame(columns=["Order ID", "Region", "Product", "Quantity ", "Unit Price", "Discount", "Order Date"])
    assert list(Pipeline.rename(raw).columns) == [
        "order_id", "region", "product", "quantity", "unit_price", "discount", "order_date",
    ]


def test_rename_raises_on_missing_column() -> None:
    with pytest.raises(ValueError, match="discount"):
        Pipeline.rename(pd.DataFrame(columns=["Order ID", "Region", "Product", "Quantity", "Unit Price", "Order Date"]))


def test_filter_valid_order_ids() -> None:
    df = pd.DataFrame({"order_id": [" SO-1 ", "Order ID", "TOTAL", "x"]})
    assert Pipeline.filter_valid_order_ids(df)["order_id"].tolist() == ["SO-1"]


def test_align_region_naming() -> None:
    df = pd.DataFrame({"region": [" south  ", "EAST", "north west", ""]})
    assert Pipeline.align_region_naming(df)["region"].tolist() == ["South", "East", "North West", "Unknown"]


def test_parse_quantity() -> None:
    df = pd.DataFrame({"quantity": ["1 762", "-3", "5", "0", "abc", "", "1.5"]})
    result = Pipeline.parse_quantity(df)
    assert result["quantity"].tolist() == [1762, -3, 5]
    assert result["quantity"].dtype == "Int64"


def test_parse_unit_price() -> None:
    df = pd.DataFrame({"unit_price": ["39,90", "21.00", "", "39.9"]})
    result = Pipeline.parse_unit_price(df)["unit_price"]
    assert result.iloc[:2].tolist() == [39.9, 21.0]
    assert result.iloc[2:].isna().all()


def test_replace_na_discount() -> None:
    df = pd.DataFrame({"discount": ["", "12.50", "abc"]})
    assert Pipeline.replace_na_discount(df)["discount"].tolist() == [0.0, 12.5]


def test_drop_duplicates() -> None:
    df = pd.DataFrame({"order_id": ["SO-1", "SO-1", "SO-2"], "quantity": [1, 1, 1]})
    assert Pipeline.drop_duplicates(df)["order_id"].tolist() == ["SO-1", "SO-2"]


def test_fill_missing_unit_price() -> None:
    df = pd.DataFrame({
        "order_id": ["SO-1", "SO-2", "SO-3", "SO-4", "SO-5", "SO-6"],
        "product": ["Mouse", "Mouse", "Ghost", "Lamp", "Lamp", "Lamp"],
        "unit_price": [10.0, np.nan, np.nan, 4.0, 5.0, np.nan],
    })
    result = Pipeline.fill_missing_unit_price(df)
    assert result["order_id"].tolist() == ["SO-1", "SO-2", "SO-4", "SO-5"]
    assert result["unit_price"].tolist() == [10.0, 10.0, 4.0, 5.0]


def test_extract_footer() -> None:
    df = pd.DataFrame({"order_id": ["SO-1", "TOTAL"], "quantity": ["1", "1 000"], "discount": ["", "12,50"]})
    assert Pipeline.extract_footer(df) == {"quantity": 1000.0, "discount": 12.5}
    assert Pipeline.extract_footer(df.iloc[:1]) is None


def test_check_with_footer_warns_on_mismatch(caplog: pytest.LogCaptureFixture) -> None:
    df = pd.DataFrame({"quantity": [1, 2], "discount": [0.0, 1.0]})
    with caplog.at_level(logging.WARNING):
        Pipeline.check_with_footer(df, {"quantity": 3.0, "discount": 5.0})
    assert "discount sum 1.00 does not match footer 5.00" in caplog.text
    assert "quantity" not in caplog.text


def test_add_revenue_rounds_to_cents() -> None:
    df = pd.DataFrame({"quantity": [3, -1], "unit_price": [3.333, 10.0], "discount": [0.0, 0.0]})
    assert Pipeline.add_revenue(df)["revenue"].tolist() == [10.0, -10.0]


def test_add_revenue_raises_when_column_missing() -> None:
    with pytest.raises(ValueError):
        Pipeline.add_revenue(pd.DataFrame({"quantity": [1], "unit_price": [1.0]}))


def test_aggregate_revenue_by_region() -> None:
    df = pd.DataFrame({"region": ["East", "West", "East"], "revenue": [1.0, 5.0, 2.5]})
    result = Pipeline.aggregate_revenue_by_region(df)
    assert result.to_dict("list") == {"region": ["West", "East"], "total_revenue": [5.0, 3.5]}


# --- end-to-end ---

SYNTHETIC_CSV = """\
Order ID,Region,Product,Quantity ,Unit Price,Discount,Order Date
SO-1,North,Mouse,2,10.00,,2026-01-01
SO-2, north ,Mouse,1 000,10.00,5.00,2026-01-02
Order ID,Region,Product,Quantity ,Unit Price,Discount,Order Date
SO-3,SOUTH,Lamp,3,"4,50",,2026-01-03
SO-3,SOUTH,Lamp,3,"4,50",,2026-01-03
SO-4,south,Mouse,-1,10.00,,2026-01-04
SO-5,South,Lamp,4,,,2026-01-05
TOTAL,,,1011,,5.00,
"""
# North: 2 * 10 + (1000 * 10 - 5)          = 10015.00
# South: 3 * 4.5 (duplicate dropped) - 10 + 4 * 4.5 (price filled) = 21.50


def test_run_on_synthetic_file(tmp_path, caplog: pytest.LogCaptureFixture) -> None:
    input_path, output_path = tmp_path / "sales.csv", tmp_path / "out.csv"
    input_path.write_text(SYNTHETIC_CSV)

    with caplog.at_level(logging.INFO):
        result = Pipeline.run(str(input_path), str(output_path))

    expected = {"region": ["North", "South"], "total_revenue": [10015.0, 21.5]}
    assert result.to_dict("list") == expected
    assert pd.read_csv(output_path).to_dict("list") == expected
    assert "does not match footer" not in caplog.text


def test_run_on_sales_csv(tmp_path) -> None:
    """ Regression snapshot of the real data. Update deliberately if the cleaning rules change. """
    result = Pipeline.run("sales.csv", str(tmp_path / "out.csv"))
    assert dict(zip(result["region"], result["total_revenue"])) == pytest.approx({
        "North": 665897.52,
        "Central": 515824.67,
        "South": 504036.04,
        "West": 442268.89,
        "East": 442219.91,
    })
