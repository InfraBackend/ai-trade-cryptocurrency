"""
Enhanced AI Trading Prompts
"""

def get_enhanced_trading_prompt(market_state, portfolio, account_info, system_prompt=""):
    """Generate enhanced trading prompt with comprehensive market analysis"""
    
    # Use custom system prompt if provided
    if system_prompt.strip():
        system_role = system_prompt.strip()
    else:
        system_role = """You are an expert cryptocurrency trader with 10+ years of experience in digital asset markets. 
You have deep knowledge of technical analysis, risk management, and market psychology. 
Your trading decisions are based on comprehensive analysis of multiple factors."""
    
    prompt = f"""{system_role}

🔍 MARKET ANALYSIS FRAMEWORK:

📊 CURRENT MARKET DATA:
"""
    
    # Enhanced market data presentation
    for coin, data in market_state.items():
        price = data['price']
        change_24h = data['change_24h']
        
        # Market sentiment based on price change
        if change_24h > 5:
            sentiment = "🟢 BULLISH"
        elif change_24h > 2:
            sentiment = "🟡 POSITIVE"
        elif change_24h > -2:
            sentiment = "⚪ NEUTRAL"
        elif change_24h > -5:
            sentiment = "🟠 NEGATIVE"
        else:
            sentiment = "🔴 BEARISH"
        
        prompt += f"""
{coin}: ${price:.2f} ({change_24h:+.2f}%) {sentiment}"""
        
        if 'indicators' in data and data['indicators']:
            indicators = data['indicators']
            sma7 = indicators.get('sma_7', 0)
            sma14 = indicators.get('sma_14', 0)
            rsi = indicators.get('rsi_14', 50)
            
            # Technical analysis
            trend = "↗️ UPTREND" if sma7 > sma14 else "↘️ DOWNTREND"
            rsi_signal = "🔥 OVERBOUGHT" if rsi > 70 else "❄️ OVERSOLD" if rsi < 30 else "⚖️ NEUTRAL"
            
            prompt += f"""
  📈 Technical: SMA7: ${sma7:.2f}, SMA14: ${sma14:.2f} {trend}
  📊 RSI: {rsi:.1f} {rsi_signal}
  💹 7D Change: {indicators.get('price_change_7d', 0):+.1f}%"""
    
    # Account analysis
    total_return = account_info['total_return']
    performance_emoji = "🚀" if total_return > 10 else "📈" if total_return > 0 else "📉" if total_return > -10 else "💥"
    
    prompt += f"""

💼 ACCOUNT STATUS:
- Initial Capital: ${account_info['initial_capital']:,.2f}
- Current Value: ${portfolio['total_value']:,.2f}
- Available Cash: ${portfolio['cash']:,.2f}
- Total Return: {total_return:+.2f}% {performance_emoji}
- Positions Value: ${portfolio.get('positions_value', 0):,.2f}

📋 CURRENT POSITIONS ({len(portfolio.get('positions', []))}/3):"""
    
    if portfolio['positions']:
        for pos in portfolio['positions']:
            side_emoji = "🟢" if pos['side'] == 'long' else "🔴"
            current_price = market_state.get(pos['coin'], {}).get('price', pos['avg_price'])
            pnl_pct = ((current_price - pos['avg_price']) / pos['avg_price'] * 100) if pos['side'] == 'long' else ((pos['avg_price'] - current_price) / pos['avg_price'] * 100)
            pnl_emoji = "💰" if pnl_pct > 0 else "💸"
            
            prompt += f"""
- {side_emoji} {pos['coin']} {pos['side'].upper()}: {pos['quantity']:.4f} @ ${pos['avg_price']:.2f}
  Current: ${current_price:.2f} | P&L: {pnl_pct:+.1f}% {pnl_emoji} | Leverage: {pos['leverage']}x"""
    else:
        prompt += "\n- No open positions"
    
    prompt += """

🎯 TRADING STRATEGY FRAMEWORK:

1. 📊 TECHNICAL ANALYSIS:
   - Trend Analysis: Use SMA crossovers for trend direction
   - Momentum: RSI for overbought/oversold conditions
   - Support/Resistance: Consider price levels and volume

2. 🧠 MARKET PSYCHOLOGY:
   - Fear & Greed: Contrarian approach during extreme sentiment
   - News Impact: Consider recent developments and market reactions
   - Volume Analysis: Confirm price movements with volume

3. ⚖️ RISK MANAGEMENT (CRITICAL):
   - Maximum 3 positions simultaneously
   - Risk 1-3% of account per trade (conservative approach)
   - Use stop losses: -5% for risk control
   - Take profits: +10-20% depending on market conditions
   - Maximum leverage: 10x (lower is safer)

4. 💰 POSITION SIZING:
   - Small positions: 1-2% risk (uncertain setups)
   - Medium positions: 2-3% risk (good setups)
   - Never risk more than 3% on a single trade

5. 🚨 EXIT RULES:
   - Stop Loss: -5% from entry (non-negotiable)
   - Take Profit: +15% for swing trades, +10% for scalps
   - Trailing stops: Move stop to breakeven after +8% gain

📋 DECISION MATRIX:

BULLISH SIGNALS (BUY):
- RSI < 40 + Uptrend (SMA7 > SMA14)
- Strong 24h performance (>3%) + Volume confirmation
- Oversold bounce opportunity

BEARISH SIGNALS (SELL/SHORT):
- RSI > 60 + Downtrend (SMA7 < SMA14)  
- Weak 24h performance (<-3%) + Volume confirmation
- Overbought correction opportunity

HOLD SIGNALS:
- Unclear trend direction
- Low conviction setups
- Risk limits already reached

🎯 OUTPUT FORMAT (JSON ONLY):
```json
{
  "COIN": {
    "signal": "buy_to_enter|sell_to_enter|hold|close_position",
    "quantity": 0.5,
    "leverage": 5,
    "profit_target": 45000.0,
    "stop_loss": 42000.0,
    "confidence": 0.75,
    "justification": "Detailed technical and fundamental reasoning (2-3 sentences)",
    "risk_assessment": "low|medium|high",
    "time_horizon": "scalp|swing|position"
  }
}
```

⚠️ CRITICAL REMINDERS:
- NEVER exceed 3 positions
- ALWAYS set stop losses
- NEVER risk more than 3% per trade
- Consider market correlation (don't buy multiple correlated assets)
- Quality over quantity - wait for high-probability setups

Analyze the current market conditions and provide your trading decisions in JSON format only."""
    
    return prompt