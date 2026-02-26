# Polymarket Trading Bot - Project Summary

## Project Goal
Build an automated trading bot for Polymarket binary markets.
Strategy: buy both Yes/No sides at 50/50, profit from human overreaction.

## GitHub
https://github.com/BenjaminPoyet/polymarket-simulator

## Files
- polymarket_app.py: Main Streamlit app (simulator, scanner, trades tracker)
- data_collector.py: Collects BTC odds every 30 seconds to odds_history.csv
- historical_analysis.py: Backtests Rule 1 and Rule 2 on historical data
- polymarket.py: Core simulation logic

## Trading Strategy
### Rule 1 (VALIDATED - 95.8% win rate):
- After 70% time consumed
- Either side hits 75%+
- Sell loser immediately
- Hold winner to resolution
- Risk: thin margins, sensitive to spread and liquidity

### Rule 2 (REJECTED by data):
- Early spike to 90% in first 33% of time
- Abandoned - only 16.7% win rate

### Rule 3 (Middle window 33-70%):
- Unknown - needs data to decide
- Data collector running to find optimal thresholds

## Safety Parameters
- 3 sequential losses → pause bot, manual review
- 20% daily loss → stop for the day
- 20% total drawdown → stop completely

## Real Trade Calibration
- First real trade: $6 invested, +$0.20 profit, 1 hour
- Illiquidity haircut: 72% (sold loser at 7¢ instead of 25¢)
- Key insight: liquidity is #1 variable

## Tech Stack
- Python + Streamlit: app and simulation
- Supabase: customer and trade database
- Oracle Cloud: 24/7 bot hosting (free)
- Alchemy API: blockchain payment detection
- GitHub: code storage and CI/CD
- Streamlit Cloud: public deployment

## Monetization Plan
- Free tier: simulator + scanner
- Paid 5 USDC/month: full scanner + alerts
- Paid 10 USDC/month: bot access
- Payment: direct USDC on Polygon (0% fees)
- Loss leader: free app builds trust via public wallet P&L

## Current Status
✅ Simulator with Monte Carlo
✅ Dark theme UI
✅ Scanner with filters
✅ Real trades wallet tracker
✅ Data collector running (BTC only)
✅ GitHub repository
⏳ Fix Polymarket two-account issue (BLOCKER)
⏳ Strategy optimizer
⏳ Bot execution layer
⏳ Streamlit Cloud deployment
⏳ Payment system

## Roadmap
1. Fix Polymarket account
2. Run strategy optimizer on collected data
3. Build trading bot execution
4. Deploy to Streamlit Cloud
5. Add payment system
6. Launch beta (free)
7. Convert to paid tier
8. Smart contract profit share (long term)

## Future Projects
- Flight simulator (Three.js)
- Rocket launch simulator
- Strip club parking economic indicator
