# Configuration Example

# Server
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False

# Database
DATABASE_PATH = 'trading_bot.db'

# Trading
AUTO_TRADING = True
TRADING_INTERVAL = 180  # seconds
COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']

# Market Data
MARKET_API_CACHE = 5  # seconds
MARKET_API_URL = 'https://api.coingecko.com/api/v3'

# Refresh Rates (frontend)
MARKET_REFRESH = 5000  # ms
PORTFOLIO_REFRESH = 10000  # ms

# OKX Configuration (Optional)
# Set these environment variables for enhanced security
# export TRADING_BOT_SECRET_KEY="your-secret-key-for-encryption"

# OKX API Settings
OKX_SANDBOX_URL = 'https://www.okx.com'  # Same URL for sandbox and live
OKX_LIVE_URL = 'https://www.okx.com'

# Rate Limiting (OKX API Limits)
OKX_MAX_REQUESTS_PER_SECOND = 10
OKX_MAX_REQUESTS_PER_MINUTE = 600
OKX_MIN_REQUEST_INTERVAL = 0.1  # seconds

# Security Settings
ENCRYPT_API_CREDENTIALS = True  # Enable credential encryption
CREDENTIAL_ENCRYPTION_KEY = None  # Auto-generated if not set

# Example OKX Model Configuration (via Web Interface)
EXAMPLE_OKX_CONFIG = {
    "name": "My OKX Trading Bot",
    "api_key": "sk-your-ai-api-key",
    "api_url": "https://api.openai.com",
    "model_name": "gpt-4",
    "initial_capital": 10000,
    "okx_api_key": "your-okx-api-key",
    "okx_secret_key": "your-okx-secret-key", 
    "okx_passphrase": "your-okx-passphrase",
    "okx_sandbox_mode": True  # Start with sandbox for testing
}

