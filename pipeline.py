import logging
import re
import pandas as pd
from solution import add_virtual_column

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = ["order_id", "region", "product", "quantity", "unit_price", "discount", "order_date"]
ORDER_ID_PATTERN = r"SO-\d+"
QUANTITY_PATTERN = r"-?\d+"
PRICE_PATTERN = r"\d+\.\d{2}"
DISCOUNT_PATTERN = r"\d+(\.\d{1,2})?"
DATE_FORMAT = "%Y-%m-%d"
FOOTER_ID = "TOTAL"
UNKNOWN_REGION = "Unknown"


def to_snake_case(name: str) -> str:
    """ Rename a column name to snake case. """
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name.strip())
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name)
    return name.strip("_").lower()


class Pipeline:
    """ Clean sales.csv and aggregate revenue per region. """

    @staticmethod
    def read_csv(path: str) -> pd.DataFrame:
        """ Read the raw file as strings, so that every cleaning step works on exactly what was exported. """
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        logger.info("read %d rows from %s", len(df), path)
        return df

    @staticmethod
    def rename(df: pd.DataFrame) -> pd.DataFrame:
        """ Rename the columns and check that all expected columns are present. """
        df_renamed = df.rename(columns=to_snake_case)
        missing = set(EXPECTED_COLUMNS) - set(df_renamed.columns)
        if missing:
            raise ValueError(f"missing columns after rename: {sorted(missing)}")
        return df_renamed

    @staticmethod
    def extract_footer(df: pd.DataFrame) -> dict[str, float] | None:
        """ Read the totals from the TOTAL footer row, if the export has one. """
        footer = df.loc[df["order_id"].str.strip() == FOOTER_ID]
        if footer.empty:
            return None
        row = footer.iloc[-1]
        return {
            "quantity": float(row["quantity"].replace(" ", "")),
            "discount": float(row["discount"].replace(",", ".")),
        }

    @staticmethod
    def filter_valid_order_ids(df: pd.DataFrame) -> pd.DataFrame:
        """ Filter only ids with the SO-[num] pattern. Removes repeated headers and the TOTAL footer. """
        ids = df["order_id"].str.strip()
        mask = ids.str.fullmatch(ORDER_ID_PATTERN)

        is_header = ids.eq("Order ID")
        is_footer = ids.eq(FOOTER_ID)
        other = ~mask & ~is_header & ~is_footer
        logger.info(
            "order_id: removed %d repeated header row(s), %d footer row(s), %d other invalid row(s)",
            is_header.sum(), is_footer.sum(), other.sum(),
        )
        if other.any():
            logger.warning("invalid order ids: %s", ids[other].tolist())

        return df.loc[mask].assign(order_id=ids[mask]).reset_index(drop=True)

    @staticmethod
    def align_region_naming(df: pd.DataFrame) -> pd.DataFrame:
        """ Each region needs to start with an uppercase. Missing regions are 'Unknown'. """
        region = (
            df["region"]
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .str.title()
        )
        logger.info("region: normalised %d value(s)", (region != df["region"]).sum())

        is_missing = region.eq("")
        if is_missing.any():
            logger.warning("region: %d missing value(s) set to %r", is_missing.sum(), UNKNOWN_REGION)
        return df.assign(region=region.mask(is_missing, UNKNOWN_REGION))

    @staticmethod
    def strip_product(df: pd.DataFrame) -> pd.DataFrame:
        """ Remove leading and trailing whitespace from product names. """
        return df.assign(product=df["product"].str.strip())

    @staticmethod
    def parse_quantity(df: pd.DataFrame) -> pd.DataFrame:
        """ Quantity needs to be a non-zero integer. Thousands separators are removed, negative values are returns. """
        raw = df["quantity"].str.strip()
        cleaned = raw.str.replace(r"\s+", "", regex=True)
        qty = pd.to_numeric(cleaned.where(cleaned.str.fullmatch(QUANTITY_PATTERN)), errors="coerce").astype("Int64")

        is_invalid = qty.isna() | qty.eq(0)
        logger.info("quantity: removed thousands separator in %d row(s)", (cleaned != raw).sum())
        logger.info("quantity: %d negative value(s) kept as returns", (qty < 0).sum())
        if is_invalid.any():
            logger.warning("quantity: dropped %d row(s) with invalid value: %s", is_invalid.sum(), raw[is_invalid].tolist())

        return df.loc[~is_invalid].assign(quantity=qty[~is_invalid]).reset_index(drop=True)

    @staticmethod
    def parse_unit_price(df: pd.DataFrame) -> pd.DataFrame:
        """ Unit price needs to be a number with two decimal places. A decimal comma is accepted. Missing stays NaN. """
        raw = df["unit_price"].str.strip()
        cleaned = raw.str.replace(",", ".", regex=False)
        is_valid = cleaned.str.fullmatch(PRICE_PATTERN)
        price = pd.to_numeric(cleaned.where(is_valid), errors="coerce")

        is_bad_format = ~is_valid & raw.ne("")
        logger.info("unit_price: replaced decimal comma in %d row(s)", raw.str.contains(",", regex=False).sum())
        logger.info("unit_price: %d missing value(s)", raw.eq("").sum())
        if is_bad_format.any():
            logger.warning("unit_price: %d value(s) with invalid format set to missing: %s", is_bad_format.sum(), raw[is_bad_format].tolist())

        return df.assign(unit_price=price)

    @staticmethod
    def replace_na_discount(df: pd.DataFrame) -> pd.DataFrame:
        """ No discount (empty) should become 0. Rows with an unparseable discount are dropped. """
        raw = df["discount"].str.strip()
        is_empty = raw.eq("")
        is_valid = raw.str.fullmatch(DISCOUNT_PATTERN)
        is_invalid = ~is_empty & ~is_valid

        discount = pd.to_numeric(raw.where(is_valid), errors="coerce").fillna(0.0)
        logger.info("discount: %d empty value(s) set to 0", is_empty.sum())
        if is_invalid.any():
            logger.warning("discount: dropped %d row(s) with invalid value: %s", is_invalid.sum(), raw[is_invalid].tolist())

        return df.loc[~is_invalid].assign(discount=discount[~is_invalid]).reset_index(drop=True)

    @staticmethod
    def cast_order_date_to_datetime(df: pd.DataFrame) -> pd.DataFrame:
        """ Cast order date to datetime. Invalid dates become NaT; the row is kept because revenue does not depend on it. """
        order_date = pd.to_datetime(df["order_date"].str.strip(), format=DATE_FORMAT, errors="coerce")
        if order_date.isna().any():
            logger.warning("order_date: %d invalid value(s) set to NaT", order_date.isna().sum())
        return df.assign(order_date=order_date)

    @staticmethod
    def check_with_footer(df: pd.DataFrame, footer: dict[str, float] | None) -> None:
        """ Compare column sums with the TOTAL footer. Must run before dedup. """
        if footer is None:
            logger.info("reconcile: no footer row, skipped")
            return
        for column, expected in footer.items():
            actual = round(float(df[column].sum()), 2)
            if abs(actual - expected) > 0.005:
                logger.warning("reconcile: %s sum %.2f does not match footer %.2f", column, actual, expected)
            else:
                logger.info("reconcile: %s sum %.2f matches footer", column, actual)

    @staticmethod
    def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
        """ Remove exact duplicate order lines, compared after cleaning. """
        is_duplicate = df.duplicated()
        logger.info("duplicates: dropped %d row(s): %s", is_duplicate.sum(), df.loc[is_duplicate, "order_id"].tolist())
        return df.loc[~is_duplicate].reset_index(drop=True)

    @staticmethod
    def fill_missing_unit_price(df: pd.DataFrame) -> pd.DataFrame:
        """ Fill a missing unit price with the product's price, if the product has exactly one known price. """
        known = df.dropna(subset=["unit_price"]).groupby("product")["unit_price"]
        n_prices = known.nunique()
        ambiguous = n_prices[n_prices > 1].index.tolist()
        if ambiguous:
            logger.warning("unit_price: products with more than one price, not used for filling: %s", ambiguous)
        price_lookup = known.first().drop(ambiguous)

        is_missing = df["unit_price"].isna()
        price = df["unit_price"].fillna(df["product"].map(price_lookup))
        is_unfixable = price.isna()
        logger.info("unit_price: filled %d missing value(s) from product price", (is_missing & ~is_unfixable).sum())
        if is_unfixable.any():
            logger.warning("unit_price: dropped %d row(s) without a known price: %s", is_unfixable.sum(), df.loc[is_unfixable, "order_id"].tolist())

        return df.loc[~is_unfixable].assign(unit_price=price[~is_unfixable]).reset_index(drop=True)

    @staticmethod
    def add_revenue(df: pd.DataFrame) -> pd.DataFrame:
        """ Add revenue columns, which contains a calculation. Rounded to two decimal places per line. """
        df_revenue = add_virtual_column(df, "quantity * unit_price - discount", "revenue")
        if df_revenue.empty:
            raise ValueError("add_virtual_column returned an empty DataFrame; check the column names in the role")
        return df_revenue.assign(revenue=df_revenue["revenue"].round(2))

    @staticmethod
    def aggregate_revenue_by_region(df: pd.DataFrame) -> pd.DataFrame:
        """ Total revenue per region, highest first. """
        return (
            df.groupby("region", as_index=False)["revenue"]
            .sum()
            .rename(columns={"revenue": "total_revenue"})
            .round({"total_revenue": 2})
            .sort_values("total_revenue", ascending=False, ignore_index=True)
        )

    @staticmethod
    def write_csv(df: pd.DataFrame, path: str = "revenue_by_region.csv") -> None:
        """ Write a DataFrame to CSV without the index. """
        df.to_csv(path, index=False)
        logger.info("wrote %d rows to %s", len(df), path)

    @staticmethod
    def run(input_path: str = "sales.csv", output_path: str = "revenue_by_region.csv") -> pd.DataFrame:
        """ Run all steps in order and return the aggregated revenue. """
        df = Pipeline.read_csv(input_path)
        df = Pipeline.rename(df)
        footer = Pipeline.extract_footer(df)
        df = Pipeline.filter_valid_order_ids(df)
        df = Pipeline.align_region_naming(df)
        df = Pipeline.strip_product(df)
        df = Pipeline.parse_quantity(df)
        df = Pipeline.parse_unit_price(df)
        df = Pipeline.replace_na_discount(df)
        df = Pipeline.cast_order_date_to_datetime(df)
        Pipeline.check_with_footer(df, footer)
        df = Pipeline.drop_duplicates(df)
        df = Pipeline.fill_missing_unit_price(df)
        df = Pipeline.add_revenue(df)
        logger.info("clean order lines: %d", len(df))

        df_agg = Pipeline.aggregate_revenue_by_region(df)
        Pipeline.write_csv(df_agg, output_path)
        return df_agg


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(Pipeline.run())
