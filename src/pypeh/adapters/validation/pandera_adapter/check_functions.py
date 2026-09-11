"""Validation check functions for dataframes.

These functions extend the validation library with PEH-specific checks.

You can add your own validation functions by creating a new function in this file.

When to add a new function:
- If you need to validate a specific condition that is not covered by the existing functions.

# TODO: Point to the documentation for the validation library
The following functions are available in the validation library:
    - 'is_equal_to'
    - 'is_equal_to_or_both_missing'
    - 'is_greater_than_or_equal_to'
    - 'is_greater_than'
    - 'is_less_than_or_equal_to'
    - 'is_less_than':
    - 'is_not_equal_to'
    - 'is_not_equal_to_and_not_both_missing'
    - 'is_unique'
    - 'is_duplicated'
    - 'is_in'
    - 'is_null'
    - 'is_not_null'

You can use these functions as steps to create:
    - 'validation_condition_expression'
    - 'validation_conjunction_expression'
    - 'validation_disjunction_expression'

As I rule of thumb, if you need to calculate an intermediate step that does not evaluate
to booleans, you need to create a new function.

Each function must follow this signature:

```python
def function_name(
    data: pa.PolarsData,
    arg_values: Sequence[Any] | None = None,
    arg_columns: Sequence[str] | None = None,
    subject: Sequence[str] | None = None,
) -> pl.LazyFrame:
    pass
```

Example:
In this example, we need to validate the length of a string column as being 3 characters.
As is the valid length of a code type, for example ISO 3166 (country code).

```python
def string_length(
    data: pa.PolarsData,
    arg_values: Sequence[Any] | None = None,
    arg_columns: Sequence[str] | None = None,
    subject: Sequence[str] | None = None,
) -> pl.LazyFrame:
    return data.lazyframe.select(
        # select the column
        pl.col(data.key)
        # step 1 - Get column as string -> return strings
        .str
        # step 2 - Get the length of the string -> returns integers
        .lengths()
        # step 3 - Check if the length is equal to 3 -> return booleans
        .eq(3)
    )

```
P.S.: This is a contrived example, but it shows how to create a new function. In this case,
it would be better to use a list of categories.

"""

from typing import Any, Sequence

import pandera.polars as pa
import polars as pl


AVAILABLE_CHECKS = {
    "is_equal_to",
    "is_equal_to_or_both_missing",
    "is_greater_than_or_equal_to",
    "is_greater_than",
    "is_less_than_or_equal_to",
    "is_less_than",
    "is_not_equal_to",
    "is_not_equal_to_and_not_both_missing",
    "is_unique",
    "is_duplicated",
    "is_in",
    "is_null",
    "is_not_null",
}


def decimals_precision(data, arg_values, arg_columns=None, subject=None):
    precision = arg_values[0]
    col = pl.col(data.key).cast(pl.Float64)
    # A value respects the precision if rounding it to `precision` decimals
    # leaves it unchanged. Comparison is done at the value's own magnitude
    # (rather than scaling by 10**precision) so that float representation
    # error does not grow with the number of decimals and produce false
    # positives. The tolerance scales with magnitude to stay above the ULP.
    tolerance = 1e-9 * col.abs().clip(lower_bound=1.0)
    return data.lazyframe.select(
        (col - col.round(precision)).abs().le(tolerance) | col.is_null()
    )


def trailing_spaces(
    data: pa.PolarsData,
    arg_values: Sequence[Any] | None = None,
    arg_columns: Sequence[str] | None = None,
    subject: Sequence[str] | None = None,
) -> pl.LazyFrame:
    return data.lazyframe.select(
        (
            (pl.col(data.key).cast(pl.String).str.starts_with(" ")).or_(
                pl.col(data.key).cast(pl.String).str.ends_with(" ")
            )
        ).not_()
    )


def tukey_range_check_log(
    data: pa.PolarsData,
    arg_values: Sequence[Any] | None = None,
    arg_columns: Sequence[str] | None = None,
    subject: Sequence[str] | None = None,
) -> pl.LazyFrame:
    key = data.key
    lf = data.lazyframe

    stats_lf = lf.select(
        pl.col(key).log().quantile(0.25).alias("p25"),
        pl.col(key).log().quantile(0.75).alias("p75"),
    )
    stats_lf = (
        stats_lf.with_columns((pl.col("p75") - pl.col("p25")).alias("iqr"))
        .with_columns(
            (pl.col("p25") - 3 * pl.col("iqr")).alias("lower"),
            (pl.col("p75") + 3 * pl.col("iqr")).alias("upper"),
        )
        .select("lower", "upper")
    )
    joined = lf.join(stats_lf, how="cross")

    return joined.select(
        pl.col(key).log().is_between(pl.col("lower"), pl.col("upper"))
    )
