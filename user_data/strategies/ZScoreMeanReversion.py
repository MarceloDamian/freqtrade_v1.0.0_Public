import numpy as np
import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import DecimalParameter, IntParameter, IStrategy


def hurst_exponent(series: np.ndarray, max_lag: int = 20) -> float:
    """Hurst exponent via the lagged-variance method.

    H < 0.5  mean-reverting
    H = 0.5  random walk
    H > 0.5  trending

    tau(lag) ~ lag**H, so H is the slope of log(tau) against log(lag).
    """
    if len(series) < max_lag + 2 or np.any(~np.isfinite(series)):
        return np.nan

    lags = np.arange(2, max_lag)
    tau = np.array([np.std(series[lag:] - series[:-lag]) for lag in lags])

    # A flat window gives tau == 0 and log(0) blows up.
    if np.any(tau <= 0):
        return np.nan

    return float(np.polyfit(np.log(lags), np.log(tau), 1)[0])


class ZScoreMeanReversion(IStrategy):
    """Mean reversion on the z-score of log price, gated by a Hurst regime filter.

    The math lives in three places, which is the point of this file:
      1. populate_indicators  - compute the quantities
      2. populate_*_trend     - turn them into boolean conditions
      3. *Parameter objects   - expose the constants to hyperopt
    """

    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    # Deliberately unreachable, so exits come from the signal rather than from a
    # fixed ROI ladder. A low ROI target manufactures winners and hides the truth.
    minimal_roi = {"0": 10.0}

    stoploss = -0.08
    trailing_stop = False

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    startup_candle_count = 200

    # --- hyperopt search space -------------------------------------------------
    zscore_window = IntParameter(10, 100, default=30, space="buy", optimize=True)
    entry_z = DecimalParameter(-3.0, -0.5, default=-2.0, decimals=2, space="buy", optimize=True)
    exit_z = DecimalParameter(-0.5, 1.5, default=0.0, decimals=2, space="sell", optimize=True)
    hurst_max = DecimalParameter(0.30, 0.60, default=0.50, decimals=2, space="buy", optimize=True)
    hurst_window = IntParameter(50, 150, default=100, space="buy", optimize=False)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Log price: returns become additive, which is what the z-score assumes.
        dataframe["log_close"] = np.log(dataframe["close"])

        window = int(self.zscore_window.value)
        rolling = dataframe["log_close"].rolling(window)
        mean = rolling.mean()
        std = rolling.std(ddof=0)

        # Standard score: how many sigma is price from its own recent mean.
        dataframe["zscore"] = (dataframe["log_close"] - mean) / std.replace(0, np.nan)

        # Regime filter: only fade the move when the series is actually mean-reverting.
        dataframe["hurst"] = (
            dataframe["log_close"]
            .rolling(int(self.hurst_window.value))
            .apply(lambda w: hurst_exponent(w.to_numpy()), raw=False)
        )

        # Realised volatility, annualised from hourly bars (24 * 365 hours).
        dataframe["volatility"] = (
            dataframe["log_close"].diff().rolling(window).std(ddof=0) * np.sqrt(24 * 365)
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["zscore"] < self.entry_z.value)
            & (dataframe["hurst"] < self.hurst_max.value)
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "z_below_mean")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["zscore"] > self.exit_z.value) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "reverted_to_mean")
        return dataframe
