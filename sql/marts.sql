-- Monthly view of each currency: month-end rate, monthly return and the
-- rolling volatility of daily log returns over the last 30 trading days.
CREATE OR REPLACE TABLE mart_monthly_volatility AS
WITH daily AS (
    SELECT
        currency_code,
        effective_date,
        CAST(mid_rate AS DOUBLE) AS rate,
        lag(CAST(mid_rate AS DOUBLE)) OVER (
            PARTITION BY currency_code ORDER BY effective_date
        ) AS prev_rate
    FROM fct_daily_rates
),
returns AS (
    SELECT
        *,
        -- A log return only exists between two positive rates. Bad rates get
        -- NULL here instead of crashing the build; the quality checks flag them.
        CASE WHEN rate > 0 AND prev_rate > 0 THEN ln(rate / prev_rate) END
            AS log_return
    FROM daily
),
rolling AS (
    SELECT
        *,
        stddev_samp(log_return) OVER (
            PARTITION BY currency_code
            ORDER BY effective_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS vol_30d
    FROM returns
)
SELECT
    currency_code,
    CAST(date_trunc('month', effective_date) AS DATE) AS month,
    count(*) AS trading_days,
    arg_max(rate, effective_date) AS month_end_rate,
    round(100 * (exp(sum(log_return)) - 1), 3) AS monthly_return_pct,
    round(100 * arg_max(vol_30d, effective_date), 3) AS volatility_30d_pct
FROM rolling
GROUP BY ALL
ORDER BY currency_code, month;
