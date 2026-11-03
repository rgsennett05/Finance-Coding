"""Plain-English definitions shown as tooltips (ⓘ) on the dashboard. The README glossary matches."""

GLOSSARY = {
    "Portfolio value": "Everything the account is worth right now: cash plus all stocks at today's prices.",
    "Cash": "Money not invested. The fund always keeps at least 10% of the portfolio in cash.",
    "Today": "How much the portfolio's value changed since yesterday's close.",
    "Benchmark": "VOO, a fund that tracks the S&P 500. If we can't beat simply holding VOO, the strategy isn't adding value.",
    "Price": "The latest trade price (Alpaca's free IEX feed).",
    "Today %": "Change from yesterday's closing price.",
    "Signal": "The Market Analyst's verdict: bullish (trend and momentum look strong), bearish (weak) or neutral.",
    "Score": "The Market Analyst's combined rating from −1 (very bearish) to +1 (very bullish).",
    "Owned": "Whether the fund currently holds this stock.",
    "Shares": "How many shares the fund holds (always whole shares).",
    "Avg cost": "The average price paid per share.",
    "Value": "Shares × today's price.",
    "Gain/loss $": "Profit or loss in dollars since buying, not yet locked in by selling (unrealized).",
    "Gain/loss %": "Profit or loss as a percentage of what we paid.",
    "Weight": "This stock's share of the whole portfolio. The limit is 10%; above 11% the fund trims it back.",
    "Stop-loss": "An automatic sell order 8% below what we paid, so a single stock can't lose much more than 8%.",
    "Status": "Where an order stands. 'accepted' or 'new' means waiting; 'filled' means done.",
    "Fill price": "The price the order actually traded at.",
    "12-1 momentum": "The return over the past 12 months, leaving out the most recent month — a standard way to measure a lasting trend.",
    "RSI": "Relative Strength Index, 0–100. Above 70 means heavily bought lately (overbought); below 30 means heavily sold (oversold).",
    "Volatility": "How much the price typically swings in a year. Higher means riskier.",
    "Drawdown": "The drop from a previous peak to a low. 'Worst drawdown' is the biggest such fall.",
    "Sharpe ratio": "Return per unit of risk (volatility). Higher is better; around 1 is good.",
    "Trim": "Selling part of a position that grew too big, to bring it back to the 10% limit.",
    "Cool-down": "After a stop-loss sells a stock, the fund waits 7 days before it may buy it again.",
    "Paper trading": "Practice trading with fake money on a real market. Nothing here uses real money.",
}


def helps(*columns: str) -> dict:
    """column_config for st.dataframe: a tooltip on each known column header."""
    import streamlit as st

    return {c: st.column_config.Column(help=GLOSSARY[c]) for c in columns if c in GLOSSARY}
