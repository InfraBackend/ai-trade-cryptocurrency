"""
OKX API Client Module
"""
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[WARNING] requests module not available, OKX client will work in test mode only")

import json
import time
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OKXClient:
    """OKX API Client for trading operations"""
    
    def __init__(self, api_key: str, secret_key: str, passphrase: str, sandbox: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.sandbox = sandbox

        # API endpoints
        if sandbox:
            self.base_url = "https://www.okx.com"  # OKX sandbox uses same URL but different API keys
        else:
            self.base_url = "https://www.okx.com"  # Production URL

        # Enhanced rate limiting
        self._last_request_time = {}
        self._request_counts = {}
        self._min_request_interval = 0.1  # 100ms between requests
        self._max_requests_per_second = 10  # OKX limit
        self._max_requests_per_minute = 600  # OKX limit

        # Cache
        self._cache = {}
        self._cache_time = {}
        self._cache_duration = 5  # 5 seconds cache

        # Account config cache (longer duration since it rarely changes)
        self._account_config = None
        self._account_config_time = 0
        self._account_config_duration = 300  # 5 minutes cache
    
    def _get_timestamp(self) -> str:
        """Get ISO timestamp for OKX API requests"""
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
    def _sign_request(self, method: str, endpoint: str, body: str = '') -> Dict[str, str]:
        """Generate signature for OKX API authentication"""
        timestamp = self._get_timestamp()
        
        # Create message to sign
        message = timestamp + method.upper() + endpoint + body
        
        # Create signature
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        # Return headers with proper format
        headers = {
            'Content-Type': 'application/json',
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'OK-ACCESS-TIMESTAMP': timestamp
        }
        
        # Add sandbox header if in sandbox mode
        if self.sandbox:
            headers['x-simulated-trading'] = '1'
            
        return headers
    
    def _rate_limit(self, endpoint: str):
        """Enhanced rate limiting implementation"""
        current_time = time.time()
        
        # Initialize tracking for this endpoint
        if endpoint not in self._request_counts:
            self._request_counts[endpoint] = []
        
        # Clean old requests (older than 1 minute)
        self._request_counts[endpoint] = [
            req_time for req_time in self._request_counts[endpoint]
            if current_time - req_time < 60
        ]
        
        # Check per-minute limit
        if len(self._request_counts[endpoint]) >= self._max_requests_per_minute:
            oldest_request = min(self._request_counts[endpoint])
            wait_time = 60 - (current_time - oldest_request)
            if wait_time > 0:
                print(f"[INFO] Rate limit: waiting {wait_time:.1f}s for minute window")
                time.sleep(wait_time)
                current_time = time.time()
        
        # Check per-second limit
        recent_requests = [
            req_time for req_time in self._request_counts[endpoint]
            if current_time - req_time < 1
        ]
        
        if len(recent_requests) >= self._max_requests_per_second:
            wait_time = 1.0
            print(f"[INFO] Rate limit: waiting {wait_time}s for second window")
            time.sleep(wait_time)
            current_time = time.time()
        
        # Check minimum interval
        if endpoint in self._last_request_time:
            time_diff = current_time - self._last_request_time[endpoint]
            if time_diff < self._min_request_interval:
                wait_time = self._min_request_interval - time_diff
                time.sleep(wait_time)
                current_time = time.time()
        
        # Record this request
        self._last_request_time[endpoint] = current_time
        self._request_counts[endpoint].append(current_time)
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, 
                     body: Dict = None, retry_count: int = 3) -> Dict:
        """Make HTTP request to OKX API with retry mechanism"""
        if not REQUESTS_AVAILABLE:
            raise Exception("requests module not available, cannot make HTTP requests")
            
        self._rate_limit(endpoint)
        
        url = f"{self.base_url}{endpoint}"
        
        # Prepare body
        body_str = ''
        if body:
            body_str = json.dumps(body, separators=(',', ':'))
        
        # Generate headers
        headers = self._sign_request(method, endpoint, body_str)
        
        for attempt in range(retry_count):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, params=params, headers=headers, timeout=10)
                elif method.upper() == 'POST':
                    response = requests.post(url, data=body_str, headers=headers, timeout=10)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Enhanced error handling based on HTTP status codes
                if response.status_code == 429:
                    # Rate limit exceeded
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"[WARNING] OKX rate limit exceeded, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                elif response.status_code == 401:
                    # Authentication error - don't retry
                    raise Exception(f"OKX Authentication failed: Invalid API credentials")
                elif response.status_code == 403:
                    # Permission error - don't retry
                    raise Exception(f"OKX Permission denied: Check API key permissions")
                elif response.status_code >= 500:
                    # Server error - retry
                    print(f"[WARNING] OKX server error {response.status_code}, attempt {attempt + 1}/{retry_count}")
                    if attempt < retry_count - 1:
                        time.sleep(2 ** attempt)
                        continue
                
                response.raise_for_status()
                data = response.json()
                
                # Enhanced OKX API error handling
                if 'code' in data and data['code'] != '0':
                    error_code = data['code']
                    error_msg = data.get('msg', 'Unknown OKX API error')

                    # Log detailed error information for debugging
                    print(f"[DEBUG] OKX API Error - Code: {error_code}, Message: {error_msg}")
                    print(f"[DEBUG] Full response: {json.dumps(data, indent=2)}")

                    # Check for detailed error codes in data array (for code='1')
                    detailed_error_code = None
                    detailed_error_msg = None
                    if 'data' in data and data['data'] and isinstance(data['data'], list):
                        if len(data['data']) > 0 and 'sCode' in data['data'][0]:
                            detailed_error_code = data['data'][0]['sCode']
                            detailed_error_msg = data['data'][0].get('sMsg', '')
                            print(f"[DEBUG] Detailed Error - sCode: {detailed_error_code}, sMsg: {detailed_error_msg}")

                    # Handle specific OKX error codes
                    if error_code == '1':
                        # Check if this is error 51169 (position already closed)
                        if detailed_error_code == '51169':
                            # Position already closed - include error code in exception for upper layer handling
                            raise Exception(f"OKX Error 51169: {detailed_error_msg}")
                        # Generic operation failed - usually parameter or permission issue
                        error_detail = f" (Detail: {detailed_error_code} - {detailed_error_msg})" if detailed_error_code else ""
                        raise Exception(f"OKX Operation Failed: {error_msg}{error_detail}")
                    elif error_code in ['50001', '50002', '50004']:
                        # Authentication/Permission errors - don't retry
                        raise Exception(f"OKX Auth Error {error_code}: {error_msg}")
                    elif error_code in ['50011', '50012']:
                        # Rate limit errors - retry with delay
                        print(f"[WARNING] OKX rate limit error {error_code}, attempt {attempt + 1}/{retry_count}")
                        if attempt < retry_count - 1:
                            time.sleep(5 * (attempt + 1))
                            continue
                    elif error_code in ['50013', '50014']:
                        # System errors - retry
                        print(f"[WARNING] OKX system error {error_code}, attempt {attempt + 1}/{retry_count}")
                        if attempt < retry_count - 1:
                            time.sleep(2 ** attempt)
                            continue
                    elif error_code in ['51000', '51001', '51002']:
                        # Order related errors - don't retry
                        raise Exception(f"OKX Order Error {error_code}: {error_msg}")
                    
                    raise Exception(f"OKX API Error {error_code}: {error_msg}")
                
                # Log successful request
                logger.debug(f"OKX API success: {method} {endpoint}")
                return data
                
            except requests.exceptions.Timeout:
                logger.warning(f"OKX API timeout, attempt {attempt + 1}/{retry_count}")
                if attempt == retry_count - 1:
                    raise Exception("OKX API timeout after retries")
                time.sleep(2 ** attempt)
                
            except requests.exceptions.ConnectionError:
                logger.warning(f"OKX connection error, attempt {attempt + 1}/{retry_count}")
                if attempt == retry_count - 1:
                    raise Exception("OKX connection failed after retries")
                time.sleep(2 ** attempt)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"OKX request error, attempt {attempt + 1}/{retry_count}: {e}")
                if attempt == retry_count - 1:
                    raise Exception(f"OKX request failed: {e}")
                time.sleep(2 ** attempt)
                
            except Exception as e:
                if "OKX" in str(e) and ("Auth" in str(e) or "Permission" in str(e)):
                    logger.error(f"OKX authentication/permission error: {e}")
                    raise e  # Don't retry auth/permission errors
                logger.warning(f"OKX API error, attempt {attempt + 1}/{retry_count}: {e}")
                if attempt == retry_count - 1:
                    raise e
                time.sleep(2 ** attempt)
    
    def get_account_config(self) -> Dict:
        """Get account configuration information with caching"""
        # Check cache first
        current_time = time.time()
        if self._account_config and (current_time - self._account_config_time < self._account_config_duration):
            return self._account_config

        try:
            endpoint = '/api/v5/account/config'
            response = self._make_request('GET', endpoint)

            config_data = {}

            if 'data' in response and response['data']:
                account_config = response['data'][0]
                config_data = {
                    'account_level': account_config.get('acctLv', ''),
                    'position_mode': account_config.get('posMode', ''),
                    'auto_loan': account_config.get('autoLoan', ''),
                    'permissions': account_config.get('perm', ''),
                    'uid': account_config.get('uid', ''),
                    'label': account_config.get('label', '')
                }

                print(f"[INFO] OKX Account Config: {config_data}")

                # Cache the result
                self._account_config = config_data
                self._account_config_time = current_time

            return config_data

        except Exception as e:
            print(f"[ERROR] Failed to get account config: {e}")
            # Return cached config if available, otherwise return default
            if self._account_config:
                print(f"[INFO] Using cached account config due to error")
                return self._account_config
            return {'position_mode': 'long_short_mode'}  # Default to long_short_mode
    
    def get_account_balance(self) -> Dict:
        """Get account balance information"""
        cache_key = 'account_balance'
        
        # Check cache
        if cache_key in self._cache:
            if time.time() - self._cache_time[cache_key] < self._cache_duration:
                return self._cache[cache_key]
        
        try:
            endpoint = '/api/v5/account/balance'
            response = self._make_request('GET', endpoint)
            
            balance_data = {
                'total_equity': 0,
                'available_balance': 0,
                'currencies': {}
            }
            
            # Helper function to safely convert to float
            def safe_float(value, default=0):
                if value is None or value == '' or value == 'null':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            if 'data' in response and response['data']:
                account_data = response['data'][0]
                
                # Total equity in USD
                balance_data['total_equity'] = safe_float(account_data.get('totalEq', 0))
                
                # Process currency details
                for detail in account_data.get('details', []):
                    currency = detail.get('ccy', '')
                    if currency:
                        balance_data['currencies'][currency] = {
                            'balance': safe_float(detail.get('bal', 0)),
                            'available': safe_float(detail.get('availBal', 0)),
                            'frozen': safe_float(detail.get('frozenBal', 0))
                        }
                        
                        # Calculate total available balance in USD (simplified)
                        if currency == 'USDT' or currency == 'USD':
                            balance_data['available_balance'] += safe_float(detail.get('availBal', 0))
            
            # Update cache
            self._cache[cache_key] = balance_data
            self._cache_time[cache_key] = time.time()
            
            return balance_data
            
        except Exception as e:
            print(f"[ERROR] Failed to get account balance: {e}")
            raise e
    
    def get_positions(self) -> List[Dict]:
        """Get current positions"""
        try:
            endpoint = '/api/v5/account/positions'
            response = self._make_request('GET', endpoint)
            
            positions = []
            
            if 'data' in response:
                for pos_data in response['data']:
                    # Helper function to safely convert to float
                    def safe_float(value, default=0):
                        if value is None or value == '' or value == 'null':
                            return default
                        try:
                            return float(value)
                        except (ValueError, TypeError):
                            return default
                    
                    # Get position size safely
                    pos_size = safe_float(pos_data.get('pos', 0))
                    
                    # Only include positions with non-zero size
                    if pos_size != 0:
                        position = {
                            'symbol': pos_data.get('instId', ''),
                            'side': 'long' if pos_size > 0 else 'short',
                            'size': abs(pos_size),
                            'avg_price': safe_float(pos_data.get('avgPx', 0)),
                            'mark_price': safe_float(pos_data.get('markPx', 0)),
                            'unrealized_pnl': safe_float(pos_data.get('upl', 0)),
                            'leverage': safe_float(pos_data.get('lever', 1), 1),
                            'margin': safe_float(pos_data.get('margin', 0))
                        }
                        positions.append(position)
            
            return positions
            
        except Exception as e:
            print(f"[ERROR] Failed to get positions: {e}")
            raise e
    
    def get_instrument_info(self, symbol: str) -> Dict:
        """Get instrument trading rules"""
        try:
            response = self._make_request('GET', '/api/v5/public/instruments', 
                                        params={'instType': 'SWAP', 'instId': symbol})
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            return {}
        except Exception as e:
            print(f"[WARNING] Failed to get instrument info for {symbol}: {e}")
            return {}
    
    def adjust_order_size(self, symbol: str, amount: float) -> float:
        """Adjust order size to meet instrument requirements"""
        try:
            inst_info = self.get_instrument_info(symbol)
            if inst_info:
                lot_sz = float(inst_info.get('lotSz', 1))
                min_sz = float(inst_info.get('minSz', 1))
                
                # Ensure amount meets minimum size
                if amount < min_sz:
                    amount = min_sz
                
                # Round to nearest lot size
                adjusted_amount = round(amount / lot_sz) * lot_sz
                
                # Ensure it's at least the minimum
                if adjusted_amount < min_sz:
                    adjusted_amount = min_sz
                
                if adjusted_amount != amount:
                    print(f"[INFO] Adjusted order size from {amount} to {adjusted_amount} for {symbol}")
                
                return adjusted_amount
            
            return amount
        except Exception as e:
            print(f"[WARNING] Failed to adjust order size for {symbol}: {e}")
            return amount

    def _place_close_order(self, symbol: str, side: str, amount: float, position_side: str) -> Dict:
        """Place a close position order with correct posSide based on account mode"""
        try:
            endpoint = '/api/v5/trade/order'

            # Adjust order size to meet instrument requirements
            adjusted_amount = self.adjust_order_size(symbol, amount)

            # Get account configuration to determine position mode
            account_config = self.get_account_config()
            position_mode = account_config.get('position_mode', 'long_short_mode')

            # Prepare close order data
            order_data = {
                'instId': symbol,
                'tdMode': 'cross',  # Cross margin mode
                'side': side,  # 'sell' for closing long, 'buy' for closing short
                'ordType': 'market',
                'sz': str(adjusted_amount)
            }

            # Only add posSide for long_short_mode, not for net_mode
            if position_mode == 'long_short_mode':
                order_data['posSide'] = position_side  # 'long' or 'short'
                print(f"[INFO] Using long_short_mode, posSide={position_side}")
            else:
                # In net_mode, we use 'net' or don't specify posSide
                print(f"[INFO] Using net_mode, no posSide specified")

            print(f"[INFO] Placing OKX close order: {order_data}")

            response = self._make_request('POST', endpoint, body=order_data)
            print(f"[INFO] OKX close order response: {response}")

            order_result = {
                'success': False,
                'order_id': None,
                'message': 'Close order failed'
            }

            if 'data' in response and response['data']:
                order_info = response['data'][0]
                if order_info.get('sCode') == '0':  # Success
                    order_result = {
                        'success': True,
                        'order_id': order_info.get('ordId'),
                        'client_order_id': order_info.get('clOrdId'),
                        'message': 'Close order placed successfully',
                        'original_amount': amount,
                        'adjusted_amount': adjusted_amount
                    }
                    print(f"[SUCCESS] OKX close order placed: {order_result}")
                else:
                    error_code = order_info.get('sCode', 'Unknown')
                    error_msg = order_info.get('sMsg', 'Close order failed')

                    # Handle 51169 error specially - position already closed
                    if error_code == '51169':
                        print(f"[INFO] Position already closed (Error 51169) - treating as success")
                        order_result = {
                            'success': True,
                            'order_id': None,
                            'message': 'Position already closed on exchange',
                            'already_closed': True
                        }
                    else:
                        order_result['message'] = f"Close Order Error {error_code}: {error_msg}"
                        print(f"[ERROR] OKX close order failed - Code: {error_code}, Message: {error_msg}")
            else:
                print(f"[ERROR] Invalid OKX close order response format: {response}")

            return order_result

        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Failed to place close order: {e}")

            # Check if this is a 51169 error (position already closed)
            if '51169' in error_msg:
                print(f"[INFO] Position already closed (51169 in exception) - treating as success")
                return {
                    'success': True,
                    'order_id': None,
                    'message': 'Position already closed on exchange',
                    'already_closed': True
                }

            return {
                'success': False,
                'order_id': None,
                'message': f'Close order failed: {error_msg}'
            }

    def place_order(self, symbol: str, side: str, amount: float,
                   order_type: str = 'market', price: float = None,
                   leverage: int = 1) -> Dict:
        """Place a trading order"""
        try:
            endpoint = '/api/v5/trade/order'

            # Adjust order size to meet instrument requirements
            adjusted_amount = self.adjust_order_size(symbol, amount)

            # Get account configuration to determine position mode
            account_config = self.get_account_config()
            position_mode = account_config.get('position_mode', 'long_short_mode')

            # Determine position side
            pos_side = 'long' if side.lower() in ['buy', 'long'] else 'short'

            # Prepare order data
            order_data = {
                'instId': symbol,
                'tdMode': 'cross',  # Cross margin mode
                'side': 'buy' if side.lower() in ['buy', 'long'] else 'sell',
                'ordType': order_type,
                'sz': str(adjusted_amount)
            }

            # Only add posSide for long_short_mode
            if position_mode == 'long_short_mode':
                order_data['posSide'] = pos_side
                print(f"[INFO] Using long_short_mode, posSide={pos_side}")
            else:
                print(f"[INFO] Using net_mode, no posSide specified")

            # Add price for limit orders
            if order_type == 'limit' and price:
                order_data['px'] = str(price)

            print(f"[INFO] Placing OKX order: {order_data}")

            # Set leverage if provided
            if leverage > 1:
                self._set_leverage(symbol, leverage, pos_side, position_mode)
            
            response = self._make_request('POST', endpoint, body=order_data)
            print(f"[INFO] OKX order response: {response}")
            
            order_result = {
                'success': False,
                'order_id': None,
                'message': 'Order failed'
            }
            
            if 'data' in response and response['data']:
                order_info = response['data'][0]
                if order_info.get('sCode') == '0':  # Success
                    order_result = {
                        'success': True,
                        'order_id': order_info.get('ordId'),
                        'client_order_id': order_info.get('clOrdId'),
                        'message': 'Order placed successfully',
                        'original_amount': amount,
                        'adjusted_amount': adjusted_amount
                    }
                    print(f"[SUCCESS] OKX order placed: {order_result}")
                else:
                    error_code = order_info.get('sCode', 'Unknown')
                    error_msg = order_info.get('sMsg', 'Order failed')
                    order_result['message'] = f"Order Error {error_code}: {error_msg}"
                    print(f"[ERROR] OKX order failed - Code: {error_code}, Message: {error_msg}")
            else:
                print(f"[ERROR] Invalid OKX response format: {response}")
            
            return order_result
            
        except Exception as e:
            error_msg = f'Order failed: {str(e)}'
            print(f"[ERROR] Failed to place order: {e}")
            return {
                'success': False,
                'order_id': None,
                'message': error_msg
            }
    
    def _set_leverage(self, symbol: str, leverage: int, side: str = 'long', position_mode: str = 'long_short_mode'):
        """Set leverage for a trading pair"""
        try:
            endpoint = '/api/v5/account/set-leverage'

            if position_mode == 'long_short_mode':
                # Set leverage for both long and short positions in long_short_mode
                for pos_side in ['long', 'short']:
                    leverage_data = {
                        'instId': symbol,
                        'lever': str(leverage),
                        'mgnMode': 'cross',  # Use cross margin mode
                        'posSide': pos_side  # Set for both sides
                    }

                    try:
                        self._make_request('POST', endpoint, body=leverage_data)
                        print(f"[INFO] Set leverage {leverage}x for {symbol} {pos_side} position")
                    except Exception as e:
                        print(f"[WARNING] Failed to set leverage for {pos_side}: {e}")
            else:
                # In net_mode, set leverage without posSide
                leverage_data = {
                    'instId': symbol,
                    'lever': str(leverage),
                    'mgnMode': 'cross'
                }
                try:
                    self._make_request('POST', endpoint, body=leverage_data)
                    print(f"[INFO] Set leverage {leverage}x for {symbol} (net_mode)")
                except Exception as e:
                    print(f"[WARNING] Failed to set leverage: {e}")

        except Exception as e:
            print(f"[WARNING] Failed to set leverage: {e}")
            # Don't raise exception as this might not be critical
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel an existing order"""
        try:
            endpoint = '/api/v5/trade/cancel-order'
            cancel_data = {
                'instId': symbol,
                'ordId': order_id
            }
            
            response = self._make_request('POST', endpoint, body=cancel_data)
            
            cancel_result = {
                'success': False,
                'message': 'Cancel failed'
            }
            
            if 'data' in response and response['data']:
                cancel_info = response['data'][0]
                if cancel_info.get('sCode') == '0':
                    cancel_result = {
                        'success': True,
                        'message': 'Order cancelled successfully'
                    }
                else:
                    cancel_result['message'] = cancel_info.get('sMsg', 'Cancel failed')
            
            return cancel_result
            
        except Exception as e:
            print(f"[ERROR] Failed to cancel order: {e}")
            return {
                'success': False,
                'message': f'Cancel failed: {str(e)}'
            }
    
    def get_order_status(self, symbol: str, order_id: str) -> Dict:
        """Get order status"""
        try:
            endpoint = '/api/v5/trade/order'
            params = {
                'instId': symbol,
                'ordId': order_id
            }
            
            response = self._make_request('GET', endpoint, params=params)
            
            # Helper function to safely convert to float
            def safe_float(value, default=0):
                if value is None or value == '' or value == 'null':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            if 'data' in response and response['data']:
                order_data = response['data'][0]
                return {
                    'order_id': order_data.get('ordId'),
                    'status': order_data.get('state'),
                    'filled_size': safe_float(order_data.get('fillSz', 0)),
                    'avg_price': safe_float(order_data.get('avgPx', 0)),
                    'fee': safe_float(order_data.get('fee', 0))
                }
            
            return {'status': 'not_found'}
            
        except Exception as e:
            print(f"[ERROR] Failed to get order status: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def close_position(self, symbol: str, side: str = None) -> Dict:
        """Close position (market order)"""
        try:
            # Clear position cache to get fresh data
            cache_key = 'positions'
            if cache_key in self._cache:
                del self._cache[cache_key]
                print(f"[INFO] Cleared positions cache for fresh data")

            # Get current position with fresh data
            positions = self.get_positions()
            target_position = None

            for pos in positions:
                if pos['symbol'] == symbol:
                    if side is None or pos['side'] == side:
                        target_position = pos
                        break

            if not target_position:
                print(f"[INFO] No active position found for {symbol} - may already be closed")
                return {
                    'success': True,  # Not an error - position already closed
                    'message': 'Position not found - may already be closed',
                    'already_closed': True
                }

            # Check if position size is effectively zero
            position_size = abs(float(target_position['size']))
            if position_size < 0.0001:  # Effectively zero
                print(f"[INFO] Position size for {symbol} is effectively zero - treating as closed")
                return {
                    'success': True,
                    'message': 'Position size is zero - already closed',
                    'already_closed': True
                }

            # For closing positions, we need to use the correct posSide
            position_side = target_position['side']  # 'long' or 'short'

            # Place close order with correct parameters
            close_side = 'sell' if position_side == 'long' else 'buy'

            # Use specialized close order method
            return self._place_close_order(
                symbol=symbol,
                side=close_side,
                amount=position_size,
                position_side=position_side
            )

        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Failed to close position: {e}")

            # If 51169 error, treat as already closed
            if '51169' in error_msg:
                print(f"[INFO] Position already closed (51169 error) - treating as success")
                return {
                    'success': True,
                    'message': 'Position already closed on exchange',
                    'already_closed': True
                }

            return {
                'success': False,
                'message': f'Close position failed: {error_msg}'
            }