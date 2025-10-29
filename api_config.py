"""
API Configuration for rate limiting and caching
"""

# Market Data API Configuration
MARKET_DATA_CONFIG = {
    # Cache settings
    'cache_duration': 60,  # seconds
    
    # Rate limiting settings
    'min_request_interval': 2.0,  # seconds between requests to same endpoint
    'max_requests_per_minute': 30,  # per source
    'rate_limit_window': 60,  # seconds
    
    # Timeout settings
    'binance_timeout': 10,
    'coingecko_timeout': 15,
    'okx_timeout': 15,
    
    # Retry settings
    'max_retries': 2,
    'retry_delay': 1.0,  # seconds
}

# Frontend refresh intervals (milliseconds)
FRONTEND_CONFIG = {
    'market_refresh_interval': 30000,  # 30 seconds (was 5 seconds)
    'portfolio_refresh_interval': 60000,  # 60 seconds (was 10 seconds)
    'trades_refresh_interval': 120000,  # 2 minutes
}

# Trading engine intervals (seconds)
TRADING_CONFIG = {
    'min_trading_frequency': 300,  # 5 minutes minimum
    'default_trading_frequency': 600,  # 10 minutes default
    'max_trading_frequency': 3600,  # 1 hour maximum
}

# API Error handling
ERROR_CONFIG = {
    'retry_on_429': True,  # Retry on rate limit errors
    'backoff_factor': 2.0,  # Exponential backoff
    'max_backoff_time': 60,  # Maximum wait time
}