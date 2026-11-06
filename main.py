import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

ticker = "^NSEI"

# 1. Download & Clean Data
df = yf.download(ticker, start="2026-01-01", end="2026-10-31", interval="1D", auto_adjust=True, progress=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df['Close'] = df['Close'].ffill()

# 2. Daily Returns & Technical Indicators
df['market_ret'] = df['Close'].pct_change()
df['fast_ema'] = df["Close"].ewm(span=9, adjust=False).mean()
df['slow_ema'] = df["Close"].ewm(span=21, adjust=False).mean()
# Let rolling window warmup naturally without fillna(0) to prevent early false triggers
df['avg_vol'] = df['Volume'].rolling(20).mean()

# 3. Volume-Filtered Directional Signals
cond_long = (df['fast_ema'] > df['slow_ema']) & (df['Volume'] > df['avg_vol'])
cond_short = (df['fast_ema'] < df['slow_ema']) & (df['Volume'] > df['avg_vol'])
df['signal'] = np.select([cond_long, cond_short], [1, -1], default=0)

# Causal execution lag (Zero Lookahead)
df['positions'] = df['signal'].shift(1).fillna(0)

# 4. Volatility-Targeted Risk Budgeting
target_volatility = 0.12  # 12% annualized target risk
df['daily_volatility'] = df['market_ret'].rolling(20).std()
df['annual_volatility'] = df['daily_volatility'] * np.sqrt(252)

# Corrected: Target Vol / Annualized Realized Vol
scalar = target_volatility / (df['annual_volatility'] + 1e-7)

# Shift scalar by 1 day so today's sizing uses yesterday's known volatility
df['leverage_scalar'] = scalar.shift(1).clip(lower=0.0, upper=1.5).fillna(1.0)
df['allocated_weight'] = df['positions'] * df['leverage_scalar']

# 5. Returns, Equity Curves & Drawdowns
# Subtract realistic 0.1 bps transaction friction on rebalances
turnover = df['allocated_weight'].diff().abs().fillna(0)
friction = 0.0001
df['strategy_return'] = (df['allocated_weight'] * df['market_ret']) - (turnover * friction)

df['equity'] = (1 + df['strategy_return'].fillna(0)).cumprod()
df['nifty_equity'] = (1 + df['market_ret'].fillna(0)).cumprod()

df['peak'] = df['equity'].cummax()
df['peak_nifty'] = df['nifty_equity'].cummax()

df['drawdown'] = (df['equity'] - df['peak']) / df['peak']
df['nifty_drawdown'] = (df['nifty_equity'] - df['peak_nifty']) / df['peak_nifty']

# 6. Performance Summary Metrics
strat_ret_clean = df['strategy_return'].dropna()
sharpe = (strat_ret_clean.mean() / (strat_ret_clean.std() + 1e-8)) * np.sqrt(252)
strat_total_ret = (df['equity'].iloc[-1] - 1) * 100
nifty_total_ret = (df['nifty_equity'].iloc[-1] - 1) * 100
strat_max_dd = df['drawdown'].min() * 100
nifty_max_dd = df['nifty_drawdown'].min() * 100

print("=== PROJECT 1: PERFORMANCE SUMMARY ===")
print(f"Strategy Total Return:  {strat_total_ret:+.2f}%  | Nifty Buy & Hold: {nifty_total_ret:+.2f}%")
print(f"Strategy Max Drawdown:  {strat_max_dd:.2f}%   | Nifty Max DD:     {nifty_max_dd:.2f}%")
print(f"Strategy Sharpe Ratio:  {sharpe:.2f}")

# 7. Dual-Tier Visualization
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, gridspec_kw={'height_ratios': [2.2, 1]})

# Top Tier: Cumulative Equity
ax1.plot(df.index, df['equity'], color='#0284c7', lw=1.6, label='Vol-Targeted Strategy')
ax1.plot(df.index, df['nifty_equity'], color='#94a3b8', lw=1.2, linestyle='--', label='Nifty 50 Benchmark')
ax1.set_ylabel('Portfolio Equity (Base = 1.0)', fontweight='bold')
ax1.set_title('Nifty 50: Volume-Filtered Trend & Vol-Targeting System', fontweight='bold', fontsize=12)
ax1.grid(True, linestyle='--', alpha=0.3)
ax1.legend(loc='upper left')

# Bottom Tier: Underwater Drawdowns
ax2.plot(df.index, df['drawdown'], color='#0284c7', lw=1.2, label='Strategy Drawdown')
ax2.fill_between(df.index, df['drawdown'], 0, color='#ef4444', alpha=0.3)
ax2.plot(df.index, df['nifty_drawdown'], color='#94a3b8', lw=1.0, linestyle=':', label='Nifty Drawdown')
ax2.set_ylabel('Drawdown', fontweight='bold')
ax2.grid(True, linestyle='--', alpha=0.3)
ax2.legend(loc='lower left')

plt.tight_layout()
plt.show()