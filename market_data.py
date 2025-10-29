"""
Market data module - Multi-source API integration (Binance, CoinGecko, OKX)
"""
import requests
import time
from typing import Dict, List
from api_config import MARKET_DATA_CONFIG, ERROR_CONFIG

class MarketDataFetcher:
    """Fetch real-time market data from multiple sources with fallback support"""
    
    def __init__(self):
        self.binance_base_url = "https://api.binance.com/api/v3"
        self.coingecko_base_url = "https://api.coingecko.com/api/v3"
        self.okx_base_url = "https://www.okx.com/api/v5"
        
        # Binance symbol mapping
        self.binance_symbols = {
            'BTC': 'BTCUSDT',
            'ETH': 'ETHUSDT',
            'SOL': 'SOLUSDT',
            'BNB': 'BNBUSDT',
            'XRP': 'XRPUSDT',
            'DOGE': 'DOGEUSDT'
        }
        
        # OKX symbol mapping (spot trading pairs)
        self.okx_symbols = {
            'BTC': 'BTC-USDT',
            'ETH': 'ETH-USDT',
            'SOL': 'SOL-USDT',
            'BNB': 'BNB-USDT',
            'XRP': 'XRP-USDT',
            'DOGE': 'DOGE-USDT'
        }
        
        # CoinGecko mapping for technical indicators
        self.coingecko_mapping = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'SOL': 'solana',
            'BNB': 'binancecoin',
            'XRP': 'ripple',
            'DOGE': 'dogecoin'
        }
        
        self._cache = {}
        self._cache_time = {}
        self._cache_duration = MARKET_DATA_CONFIG['cache_duration']
        
        # Rate limiting (from config)
        self._last_request_time = {}
        self._min_request_interval = MARKET_DATA_CONFIG['min_request_interval']
        self._request_counts = {}
        self._rate_limit_window = MARKET_DATA_CONFIG['rate_limit_window']
        self._max_requests_per_minute = MARKET_DATA_CONFIG['max_requests_per_minute']
    
    def _rate_limit_check(self, source: str) -> bool:
        """Check if we can make a request to the given source"""
        current_time = time.time()
        
        # Check minimum interval
        if source in self._last_request_time:
            time_diff = current_time - self._last_request_time[source]
            if time_diff < self._min_request_interval:
                print(f"[INFO] Rate limiting {source}: waiting {self._min_request_interval - time_diff:.1f}s")
                time.sleep(self._min_request_interval - time_diff)
        
        # Check requests per minute
        if source not in self._request_counts:
            self._request_counts[source] = []
        
        # Clean old requests
        self._request_counts[source] = [
            req_time for req_time in self._request_counts[source]
            if current_time - req_time < self._rate_limit_window
        ]
        
        # Check if we're over the limit
        if len(self._request_counts[source]) >= self._max_requests_per_minute:
            print(f"[WARNING] Rate limit exceeded for {source}, skipping request")
            return False
        
        # Record this request
        self._request_counts[source].append(current_time)
        self._last_request_time[source] = current_time
        return True

    def get_current_prices(self, coins: List[str]) -> Dict[str, float]:
        """Get current prices from Binance API"""
        # Check cache
        cache_key = 'prices_' + '_'.join(sorted(coins))
        if cache_key in self._cache:
            if time.time() - self._cache_time[cache_key] < self._cache_duration:
                return self._cache[cache_key]
        
        prices = {}
        
        try:
            # Check rate limit for Binance
            if not self._rate_limit_check('binance'):
                raise Exception("Binance rate limit exceeded")
            
            # Batch fetch Binance 24h ticker data
            symbols = [self.binance_symbols.get(coin) for coin in coins if coin in self.binance_symbols]
            
            if symbols:
                # Build symbols parameter
                symbols_param = '[' + ','.join([f'"{s}"' for s in symbols]) + ']'
                
                response = requests.get(
                    f"{self.binance_base_url}/ticker/24hr",
                    params={'symbols': symbols_param},
                    timeout=MARKET_DATA_CONFIG['binance_timeout']
                )
                response.raise_for_status()
                data = response.json()
                
                # Parse data
                for item in data:
                    symbol = item['symbol']
                    # Find corresponding coin
                    for coin, binance_symbol in self.binance_symbols.items():
                        if binance_symbol == symbol:
                            prices[coin] = {
                                'price': float(item['lastPrice']),
                                'change_24h': float(item['priceChangePercent'])
                            }
                            break
            
            # Update cache
            self._cache[cache_key] = prices
            self._cache_time[cache_key] = time.time()
            
            return prices
            
        except Exception as e:
            print(f"[ERROR] Binance API failed: {e}")
            # Fallback to CoinGecko
            return self._get_prices_from_coingecko(coins)
    
    def _get_prices_from_coingecko(self, coins: List[str]) -> Dict[str, float]:
        """Fallback 1: Fetch prices from CoinGecko"""
        try:
            # Check rate limit for CoinGecko
            if not self._rate_limit_check('coingecko'):
                raise Exception("CoinGecko rate limit exceeded")
                
            coin_ids = [self.coingecko_mapping.get(coin, coin.lower()) for coin in coins]
            
            response = requests.get(
                f"{self.coingecko_base_url}/simple/price",
                params={
                    'ids': ','.join(coin_ids),
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true'
                },
                timeout=MARKET_DATA_CONFIG['coingecko_timeout']
            )
            response.raise_for_status()
            data = response.json()
            
            prices = {}
            for coin in coins:
                coin_id = self.coingecko_mapping.get(coin, coin.lower())
                if coin_id in data:
                    prices[coin] = {
                        'price': data[coin_id]['usd'],
                        'change_24h': data[coin_id].get('usd_24h_change', 0)
                    }
            
            return prices
        except Exception as e:
            print(f"[ERROR] CoinGecko fallback also failed: {e}")
            # Final fallback to OKX
            return self._get_prices_from_okx(coins)
    
    def _get_prices_from_okx(self, coins: List[str]) -> Dict[str, float]:
        """Fallback 2: Fetch prices from OKX public API"""
        try:
            # Check rate limit for OKX
            if not self._rate_limit_check('okx'):
                raise Exception("OKX rate limit exceeded")
                
            prices = {}
            
            # OKX allows batch requests, so we'll get all tickers at once
            symbols = [self.okx_symbols.get(coin) for coin in coins if coin in self.okx_symbols]
            
            if symbols:
                # Get all tickers from OKX
                response = requests.get(
                    f"{self.okx_base_url}/market/tickers",
                    params={'instType': 'SPOT'},
                    timeout=MARKET_DATA_CONFIG['okx_timeout']
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') == '0' and 'data' in data:
                    # Create a mapping of symbol to data
                    ticker_data = {item['instId']: item for item in data['data']}
                    
                    # Extract prices for our coins
                    for coin in coins:
                        okx_symbol = self.okx_symbols.get(coin)
                        if okx_symbol and okx_symbol in ticker_data:
                            ticker = ticker_data[okx_symbol]
                            
                            # Calculate 24h change percentage
                            last_price = float(ticker.get('last', 0))
                            open_24h = float(ticker.get('open24h', last_price))
                            change_24h = 0
                            if open_24h > 0:
                                change_24h = ((last_price - open_24h) / open_24h) * 100
                            
                            prices[coin] = {
                                'price': last_price,
                                'change_24h': change_24h
                            }
                            
                    print(f"[INFO] Successfully fetched {len(prices)} prices from OKX")
            
            # If we still don't have all prices, try individual requests
            for coin in coins:
                if coin not in prices and coin in self.okx_symbols:
                    try:
                        symbol = self.okx_symbols[coin]
                        response = requests.get(
                            f"{self.okx_base_url}/market/ticker",
                            params={'instId': symbol},
                            timeout=5
                        )
                        response.raise_for_status()
                        data = response.json()
                        
                        if data.get('code') == '0' and 'data' in data and data['data']:
                            ticker = data['data'][0]
                            
                            last_price = float(ticker.get('last', 0))
                            open_24h = float(ticker.get('open24h', last_price))
                            change_24h = 0
                            if open_24h > 0:
                                change_24h = ((last_price - open_24h) / open_24h) * 100
                            
                            prices[coin] = {
                                'price': last_price,
                                'change_24h': change_24h
                            }
                    except Exception as e:
                        print(f"[WARNING] Failed to get {coin} price from OKX: {e}")
            
            # Fill in any missing coins with zero values
            for coin in coins:
                if coin not in prices:
                    prices[coin] = {'price': 0, 'change_24h': 0}
            
            return prices
            
        except Exception as e:
            print(f"[ERROR] OKX fallback also failed: {e}")
            # Return zero values as last resort
            return {coin: {'price': 0, 'change_24h': 0} for coin in coins}
    
    def get_market_data(self, coin: str) -> Dict:
        """Get detailed market data from CoinGecko"""
        coin_id = self.coingecko_mapping.get(coin, coin.lower())
        
        try:
            response = requests.get(
                f"{self.coingecko_base_url}/coins/{coin_id}",
                params={'localization': 'false', 'tickers': 'false', 'community_data': 'false'},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            market_data = data.get('market_data', {})
            
            return {
                'current_price': market_data.get('current_price', {}).get('usd', 0),
                'market_cap': market_data.get('market_cap', {}).get('usd', 0),
                'total_volume': market_data.get('total_volume', {}).get('usd', 0),
                'price_change_24h': market_data.get('price_change_percentage_24h', 0),
                'price_change_7d': market_data.get('price_change_percentage_7d', 0),
                'high_24h': market_data.get('high_24h', {}).get('usd', 0),
                'low_24h': market_data.get('low_24h', {}).get('usd', 0),
            }
        except Exception as e:
            print(f"[ERROR] Failed to get market data for {coin}: {e}")
            return {}
    
    def get_historical_prices(self, coin: str, days: int = 7) -> List[Dict]:
        """Get historical prices with fallback support"""
        # Try CoinGecko first
        try:
            # Check rate limit for CoinGecko
            if not self._rate_limit_check('coingecko_historical'):
                raise Exception("CoinGecko historical rate limit exceeded")
                
            coin_id = self.coingecko_mapping.get(coin, coin.lower())
            
            response = requests.get(
                f"{self.coingecko_base_url}/coins/{coin_id}/market_chart",
                params={'vs_currency': 'usd', 'days': days},
                timeout=15  # Increased timeout
            )
            response.raise_for_status()
            data = response.json()
            
            prices = []
            for price_data in data.get('prices', []):
                prices.append({
                    'timestamp': price_data[0],
                    'price': price_data[1]
                })
            
            if prices:
                return prices
                
        except Exception as e:
            print(f"[ERROR] CoinGecko historical data failed for {coin}: {e}")
        
        # Fallback to OKX historical data
        return self._get_historical_prices_from_okx(coin, days)
    
    def _get_historical_prices_from_okx(self, coin: str, days: int = 7) -> List[Dict]:
        """Get historical prices from OKX"""
        try:
            # Check rate limit for OKX
            if not self._rate_limit_check('okx_historical'):
                raise Exception("OKX historical rate limit exceeded")
                
            symbol = self.okx_symbols.get(coin)
            if not symbol:
                print(f"[WARNING] No OKX symbol mapping for {coin}")
                return []
            
            # OKX uses different time intervals
            # For 7 days, we'll use 1H candles (max 100 candles = ~4 days)
            # For longer periods, we'll use 4H or 1D candles
            if days <= 4:
                bar = '1H'
                limit = min(days * 24, 100)
            elif days <= 16:
                bar = '4H'
                limit = min(days * 6, 100)
            else:
                bar = '1D'
                limit = min(days, 100)
            
            response = requests.get(
                f"{self.okx_base_url}/market/history-candles",
                params={
                    'instId': symbol,
                    'bar': bar,
                    'limit': str(limit)
                },
                timeout=15  # Increased timeout
            )
            response.raise_for_status()
            data = response.json()
            
            prices = []
            if data.get('code') == '0' and 'data' in data:
                # OKX returns data in reverse chronological order
                # Format: [timestamp, open, high, low, close, volume, volCcy]
                for candle in reversed(data['data']):
                    prices.append({
                        'timestamp': int(candle[0]),
                        'price': float(candle[4])  # Close price
                    })
            
            print(f"[INFO] Got {len(prices)} historical prices from OKX for {coin}")
            return prices
            
        except Exception as e:
            print(f"[ERROR] Failed to get OKX historical prices for {coin}: {e}")
            return []
    
    def calculate_technical_indicators(self, coin: str) -> Dict:
        """Calculate technical indicators"""
        historical = self.get_historical_prices(coin, days=14)
        
        if not historical or len(historical) < 14:
            return {}
        
        prices = [p['price'] for p in historical]
        
        # Simple Moving Average
        sma_7 = sum(prices[-7:]) / 7 if len(prices) >= 7 else prices[-1]
        sma_14 = sum(prices[-14:]) / 14 if len(prices) >= 14 else prices[-1]
        
        # Simple RSI calculation
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]
        
        avg_gain = sum(gains[-14:]) / 14 if gains else 0
        avg_loss = sum(losses[-14:]) / 14 if losses else 0
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        return {
            'sma_7': sma_7,
            'sma_14': sma_14,
            'rsi_14': rsi,
            'current_price': prices[-1],
            'price_change_7d': ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] > 0 else 0
        }
    
    def get_data_source_status(self) -> Dict[str, str]:
        """Check the status of all data sources"""
        status = {
            'binance': 'unknown',
            'coingecko': 'unknown',
            'okx': 'unknown'
        }
        
        # Test Binance
        try:
            response = requests.get(f"{self.binance_base_url}/ping", timeout=5)
            if response.status_code == 200:
                status['binance'] = 'online'
            else:
                status['binance'] = 'offline'
        except:
            status['binance'] = 'offline'
        
        # Test CoinGecko
        try:
            response = requests.get(f"{self.coingecko_base_url}/ping", timeout=5)
            if response.status_code == 200:
                status['coingecko'] = 'online'
            else:
                status['coingecko'] = 'offline'
        except:
            status['coingecko'] = 'offline'
        
        # Test OKX
        try:
            response = requests.get(f"{self.okx_base_url}/public/time", timeout=5)
            data = response.json()
            if response.status_code == 200 and data.get('code') == '0':
                status['okx'] = 'online'
            else:
                status['okx'] = 'offline'
        except:
            status['okx'] = 'offline'
        
        return status
    
    def test_all_sources(self, test_coin: str = 'BTC') -> Dict:
        """Test all data sources with a sample request"""
        results = {
            'binance': {'status': 'failed', 'data': None, 'error': None},
            'coingecko': {'status': 'failed', 'data': None, 'error': None},
            'okx': {'status': 'failed', 'data': None, 'error': None}
        }
        
        # Test Binance
        try:
            symbol = self.binance_symbols.get(test_coin)
            if symbol:
                response = requests.get(
                    f"{self.binance_base_url}/ticker/24hr",
                    params={'symbol': symbol},
                    timeout=5
                )
                response.raise_for_status()
                data = response.json()
                results['binance'] = {
                    'status': 'success',
                    'data': {
                        'price': float(data['lastPrice']),
                        'change_24h': float(data['priceChangePercent'])
                    },
                    'error': None
                }
        except Exception as e:
            results['binance']['error'] = str(e)
        
        # Test CoinGecko
        try:
            coin_id = self.coingecko_mapping.get(test_coin, test_coin.lower())
            response = requests.get(
                f"{self.coingecko_base_url}/simple/price",
                params={
                    'ids': coin_id,
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true'
                },
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            if coin_id in data:
                results['coingecko'] = {
                    'status': 'success',
                    'data': {
                        'price': data[coin_id]['usd'],
                        'change_24h': data[coin_id].get('usd_24h_change', 0)
                    },
                    'error': None
                }
        except Exception as e:
            results['coingecko']['error'] = str(e)
        
        # Test OKX
        try:
            symbol = self.okx_symbols.get(test_coin)
            if symbol:
                response = requests.get(
                    f"{self.okx_base_url}/market/ticker",
                    params={'instId': symbol},
                    timeout=5
                )
                response.raise_for_status()
                data = response.json()
                if data.get('code') == '0' and 'data' in data and data['data']:
                    ticker = data['data'][0]
                    last_price = float(ticker.get('last', 0))
                    open_24h = float(ticker.get('open24h', last_price))
                    change_24h = 0
                    if open_24h > 0:
                        change_24h = ((last_price - open_24h) / open_24h) * 100
                    
                    results['okx'] = {
                        'status': 'success',
                        'data': {
                            'price': last_price,
                            'change_24h': change_24h
                        },
                        'error': None
                    }
        except Exception as e:
            results['okx']['error'] = str(e)
        
        return results
    
    def get_api_config_info(self) -> Dict:
        """Get current API configuration information"""
        return {
            'cache_duration': self._cache_duration,
            'min_request_interval': self._min_request_interval,
            'max_requests_per_minute': self._max_requests_per_minute,
            'rate_limit_window': self._rate_limit_window,
            'timeouts': {
                'binance': MARKET_DATA_CONFIG['binance_timeout'],
                'coingecko': MARKET_DATA_CONFIG['coingecko_timeout'],
                'okx': MARKET_DATA_CONFIG['okx_timeout']
            },
            'current_request_counts': {
                source: len(requests) for source, requests in self._request_counts.items()
            }
        }

