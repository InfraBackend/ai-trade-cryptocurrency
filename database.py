"""
Database management module
"""
import sqlite3
import json
import time
from datetime import datetime
from typing import List, Dict, Optional

# Import OKX client (optional dependency)
try:
    from okx_client import OKXClient
    OKX_AVAILABLE = True
except ImportError:
    OKX_AVAILABLE = False

# Import secure storage (optional dependency)
try:
    from secure_storage import get_secure_storage
    SECURE_STORAGE_AVAILABLE = True
except ImportError:
    SECURE_STORAGE_AVAILABLE = False
    print("[WARNING] Secure storage not available, using plain text")

class Database:
    def __init__(self, db_path: str = 'trading_bot.db'):
        self.db_path = db_path
        self._okx_cache = {}
        self._okx_cache_time = {}
        self._okx_cache_duration = 5  # 5 seconds cache
        
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Models table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                api_key TEXT NOT NULL,
                api_url TEXT NOT NULL,
                model_name TEXT NOT NULL,
                initial_capital REAL DEFAULT 10000,
                okx_api_key TEXT DEFAULT '',
                okx_secret_key TEXT DEFAULT '',
                okx_passphrase TEXT DEFAULT '',
                okx_sandbox_mode BOOLEAN DEFAULT 1,
                trading_frequency INTEGER DEFAULT 180,
                trading_coins TEXT DEFAULT 'BTC,ETH,SOL,BNB,XRP,DOGE',
                auto_trading_enabled BOOLEAN DEFAULT 1,
                system_prompt TEXT DEFAULT '',
                stop_loss_enabled BOOLEAN DEFAULT 0,
                stop_loss_percentage REAL DEFAULT 5.0,
                take_profit_enabled BOOLEAN DEFAULT 0,
                take_profit_percentage REAL DEFAULT 15.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Portfolios table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id),
                UNIQUE(model_id, coin, side)
            )
        ''')
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                signal TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                leverage INTEGER DEFAULT 1,
                side TEXT DEFAULT 'long',
                pnl REAL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                user_prompt TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                cot_trace TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        
        # Account values history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                total_value REAL NOT NULL,
                cash REAL NOT NULL,
                positions_value REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(id)
            )
        ''')
        
        # Database migration: Add OKX fields to existing models table
        self._migrate_okx_fields(cursor)
        
        # Database migration: Add new trading configuration fields
        self._migrate_trading_config_fields(cursor)
        
        # Database migration: Add stop loss/take profit configuration fields
        self._migrate_stop_loss_take_profit_fields(cursor)
        
        conn.commit()
        conn.close()
    
    def _migrate_okx_fields(self, cursor):
        """Migrate database to add OKX API fields"""
        try:
            # Check if OKX fields already exist
            cursor.execute("PRAGMA table_info(models)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Add missing OKX fields
            if 'okx_api_key' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN okx_api_key TEXT DEFAULT ""')
            if 'okx_secret_key' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN okx_secret_key TEXT DEFAULT ""')
            if 'okx_passphrase' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN okx_passphrase TEXT DEFAULT ""')
            if 'okx_sandbox_mode' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN okx_sandbox_mode BOOLEAN DEFAULT 1')
        except Exception as e:
            print(f"[INFO] OKX fields migration completed or not needed: {e}")
    
    def _migrate_trading_config_fields(self, cursor):
        """Migrate database to add trading configuration fields"""
        try:
            # Check if trading config fields already exist
            cursor.execute("PRAGMA table_info(models)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Add missing trading configuration fields
            if 'trading_frequency' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN trading_frequency INTEGER DEFAULT 180')
            if 'trading_coins' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN trading_coins TEXT DEFAULT "BTC,ETH,SOL,BNB,XRP,DOGE"')
            if 'auto_trading_enabled' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN auto_trading_enabled BOOLEAN DEFAULT 1')
            if 'system_prompt' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN system_prompt TEXT DEFAULT ""')
        except Exception as e:
            print(f"[INFO] Trading config fields migration completed or not needed: {e}")
    
    def _migrate_stop_loss_take_profit_fields(self, cursor):
        """Migrate database to add stop loss/take profit configuration fields"""
        try:
            # Check if stop loss/take profit fields already exist
            cursor.execute("PRAGMA table_info(models)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Add missing stop loss/take profit configuration fields
            if 'stop_loss_enabled' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN stop_loss_enabled BOOLEAN DEFAULT 0')
            if 'stop_loss_percentage' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN stop_loss_percentage REAL DEFAULT 5.0')
            if 'take_profit_enabled' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN take_profit_enabled BOOLEAN DEFAULT 0')
            if 'take_profit_percentage' not in columns:
                cursor.execute('ALTER TABLE models ADD COLUMN take_profit_percentage REAL DEFAULT 15.0')
        except Exception as e:
            print(f"[INFO] Stop loss/take profit fields migration completed or not needed: {e}")
    
    def _get_okx_client(self, model_id: int) -> Optional['OKXClient']:
        """Get OKX client for a model if configured"""
        if not OKX_AVAILABLE:
            return None
            
        model = self.get_model(model_id)
        if not model:
            return None
            
        # Check if OKX is configured for this model
        okx_fields = [model.get('okx_api_key'), model.get('okx_secret_key'), model.get('okx_passphrase')]
        if not all(okx_fields):
            return None
        
        # Check if any field is empty or looks like test data
        for field in okx_fields:
            if not field or field.strip() == '' or 'test' in field.lower():
                print(f"[INFO] Skipping OKX client creation - test/empty credentials detected for model {model_id}")
                return None
        
        # Decrypt OKX credentials
        okx_api_key = model['okx_api_key']
        okx_secret_key = model['okx_secret_key']
        okx_passphrase = model['okx_passphrase']
        
        if SECURE_STORAGE_AVAILABLE:
            try:
                storage = get_secure_storage()
                decrypted_api_key = storage.decrypt_single_value(model['okx_api_key'])
                decrypted_secret_key = storage.decrypt_single_value(model['okx_secret_key'])
                decrypted_passphrase = storage.decrypt_single_value(model['okx_passphrase'])
                
                # Use decrypted values if they're valid
                if decrypted_api_key and decrypted_secret_key and decrypted_passphrase:
                    okx_api_key = decrypted_api_key
                    okx_secret_key = decrypted_secret_key
                    okx_passphrase = decrypted_passphrase
                    print(f"[INFO] OKX credentials decrypted for model {model_id}")
                else:
                    print(f"[WARNING] Decrypted credentials are empty, using original values")
            except Exception as e:
                print(f"[WARNING] Failed to decrypt OKX credentials: {e}")
                # Use original values as fallback
        
        # Final check that we have valid credentials
        if not all([okx_api_key, okx_secret_key, okx_passphrase]):
            print(f"[WARNING] Invalid OKX credentials for model {model_id}")
            return None
        
        try:
            return OKXClient(
                api_key=okx_api_key,
                secret_key=okx_secret_key,
                passphrase=okx_passphrase,
                sandbox=bool(model.get('okx_sandbox_mode', True))
            )
        except Exception as e:
            print(f"[ERROR] Failed to create OKX client for model {model_id}: {e}")
            return None
    
    # ============ Model Management ============
    
    def add_model(self, name: str, api_key: str, api_url: str, 
                   model_name: str, initial_capital: float = 10000,
                   okx_api_key: str = '', okx_secret_key: str = '',
                   okx_passphrase: str = '', okx_sandbox_mode: bool = True,
                   trading_frequency: int = 180, trading_coins: str = 'BTC,ETH,SOL,BNB,XRP,DOGE',
                   auto_trading_enabled: bool = True, system_prompt: str = '',
                   stop_loss_enabled: bool = False, stop_loss_percentage: float = 5.0,
                   take_profit_enabled: bool = False, take_profit_percentage: float = 15.0) -> int:
        """Add new trading model"""
        # Encrypt OKX credentials if provided
        encrypted_okx_api_key = okx_api_key
        encrypted_okx_secret_key = okx_secret_key
        encrypted_okx_passphrase = okx_passphrase
        
        if SECURE_STORAGE_AVAILABLE and (okx_api_key or okx_secret_key or okx_passphrase):
            try:
                storage = get_secure_storage()
                if okx_api_key:
                    encrypted_okx_api_key = storage.encrypt_single_value(okx_api_key)
                if okx_secret_key:
                    encrypted_okx_secret_key = storage.encrypt_single_value(okx_secret_key)
                if okx_passphrase:
                    encrypted_okx_passphrase = storage.encrypt_single_value(okx_passphrase)
                print(f"[INFO] OKX credentials encrypted for model: {name}")
            except Exception as e:
                print(f"[WARNING] Failed to encrypt OKX credentials: {e}")
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO models (name, api_key, api_url, model_name, initial_capital,
                              okx_api_key, okx_secret_key, okx_passphrase, okx_sandbox_mode,
                              trading_frequency, trading_coins, auto_trading_enabled, system_prompt,
                              stop_loss_enabled, stop_loss_percentage, take_profit_enabled, take_profit_percentage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, api_key, api_url, model_name, initial_capital,
              encrypted_okx_api_key, encrypted_okx_secret_key, encrypted_okx_passphrase, okx_sandbox_mode,
              trading_frequency, trading_coins, auto_trading_enabled, system_prompt,
              stop_loss_enabled, stop_loss_percentage, take_profit_enabled, take_profit_percentage))
        model_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return model_id
    
    def get_model(self, model_id: int) -> Optional[Dict]:
        """Get model information with decrypted OKX credentials"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM models WHERE id = ?', (model_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
            
        model = dict(row)
        
        # Decrypt OKX credentials if they exist
        if model.get('okx_api_key') and model.get('okx_secret_key') and model.get('okx_passphrase'):
            try:
                storage = get_secure_storage()
                decrypted_api_key = storage.decrypt_single_value(model['okx_api_key'])
                decrypted_secret_key = storage.decrypt_single_value(model['okx_secret_key'])
                decrypted_passphrase = storage.decrypt_single_value(model['okx_passphrase'])
                
                # Use decrypted values if they're valid
                if decrypted_api_key and decrypted_secret_key and decrypted_passphrase:
                    model['okx_api_key'] = decrypted_api_key
                    model['okx_secret_key'] = decrypted_secret_key
                    model['okx_passphrase'] = decrypted_passphrase
                    print(f"[INFO] OKX credentials decrypted for model {model_id}")
                else:
                    print(f"[WARNING] Decrypted OKX credentials are empty for model {model_id}")
            except Exception as e:
                print(f"[WARNING] Failed to decrypt OKX credentials for model {model_id}: {e}")
        
        return model
    
    def get_all_models(self) -> List[Dict]:
        """Get all trading models with decrypted OKX credentials"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM models ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        
        models = []
        for row in rows:
            model = dict(row)
            
            # Decrypt OKX credentials if they exist
            if model.get('okx_api_key') and model.get('okx_secret_key') and model.get('okx_passphrase'):
                try:
                    storage = get_secure_storage()
                    decrypted_api_key = storage.decrypt_single_value(model['okx_api_key'])
                    decrypted_secret_key = storage.decrypt_single_value(model['okx_secret_key'])
                    decrypted_passphrase = storage.decrypt_single_value(model['okx_passphrase'])
                    
                    # Use decrypted values if they're valid
                    if decrypted_api_key and decrypted_secret_key and decrypted_passphrase:
                        model['okx_api_key'] = decrypted_api_key
                        model['okx_secret_key'] = decrypted_secret_key
                        model['okx_passphrase'] = decrypted_passphrase
                except Exception as e:
                    print(f"[WARNING] Failed to decrypt OKX credentials for model {model['id']}: {e}")
            
            models.append(model)
        
        return models
    
    def update_model(self, model_id: int, name: str, api_key: str, api_url: str, 
                    model_name: str, initial_capital: float = 100000,
                    okx_api_key: str = '', okx_secret_key: str = '', 
                    okx_passphrase: str = '', okx_sandbox_mode: bool = True,
                    trading_frequency: int = 180, trading_coins: str = 'BTC,ETH,SOL,BNB,XRP,DOGE',
                    auto_trading_enabled: bool = True, system_prompt: str = '',
                    stop_loss_enabled: bool = False, stop_loss_percentage: float = 5.0,
                    take_profit_enabled: bool = False, take_profit_percentage: float = 15.0) -> bool:
        """Update existing model"""
        try:
            # Check if model exists
            existing_model = self.get_model(model_id)
            if not existing_model:
                return False
            
            # Encrypt OKX credentials if provided
            encrypted_okx_api_key = okx_api_key
            encrypted_okx_secret_key = okx_secret_key
            encrypted_okx_passphrase = okx_passphrase
            
            if okx_api_key and okx_secret_key and okx_passphrase:
                try:
                    storage = get_secure_storage()
                    encrypted_okx_api_key = storage.encrypt_single_value(okx_api_key)
                    encrypted_okx_secret_key = storage.encrypt_single_value(okx_secret_key)
                    encrypted_okx_passphrase = storage.encrypt_single_value(okx_passphrase)
                    print(f"[INFO] OKX credentials encrypted for model update: {name}")
                except Exception as e:
                    print(f"[WARNING] Failed to encrypt OKX credentials during update: {e}")
            
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE models SET 
                    name = ?, api_key = ?, api_url = ?, model_name = ?, initial_capital = ?,
                    okx_api_key = ?, okx_secret_key = ?, okx_passphrase = ?, okx_sandbox_mode = ?,
                    trading_frequency = ?, trading_coins = ?, auto_trading_enabled = ?, system_prompt = ?,
                    stop_loss_enabled = ?, stop_loss_percentage = ?, take_profit_enabled = ?, take_profit_percentage = ?
                WHERE id = ?
            ''', (name, api_key, api_url, model_name, initial_capital,
                  encrypted_okx_api_key, encrypted_okx_secret_key, encrypted_okx_passphrase, 
                  okx_sandbox_mode, trading_frequency, trading_coins, auto_trading_enabled, 
                  system_prompt, stop_loss_enabled, stop_loss_percentage, take_profit_enabled, take_profit_percentage, model_id))
            
            updated = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            if updated:
                print(f"[INFO] Model {model_id} ({name}) updated successfully")
            
            return updated
            
        except Exception as e:
            print(f"[ERROR] Failed to update model {model_id}: {e}")
            return False
    
    def delete_model(self, model_id: int):
        """Delete model and related data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM models WHERE id = ?', (model_id,))
        cursor.execute('DELETE FROM portfolios WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM trades WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM conversations WHERE model_id = ?', (model_id,))
        cursor.execute('DELETE FROM account_values WHERE model_id = ?', (model_id,))
        conn.commit()
        conn.close()
    
    # ============ Portfolio Management ============
    
    def update_position(self, model_id: int, coin: str, quantity: float, 
                       avg_price: float, leverage: int = 1, side: str = 'long'):
        """Update position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO portfolios (model_id, coin, quantity, avg_price, leverage, side, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(model_id, coin, side) DO UPDATE SET
                quantity = excluded.quantity,
                avg_price = excluded.avg_price,
                leverage = excluded.leverage,
                updated_at = CURRENT_TIMESTAMP
        ''', (model_id, coin, quantity, avg_price, leverage, side))
        conn.commit()
        conn.close()
    
    def get_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get portfolio with positions and P&L
        
        Args:
            model_id: Model ID
            current_prices: Current market prices {coin: price} for unrealized P&L calculation
        """
        # Try to get data from OKX first, fallback to local simulation
        okx_client = self._get_okx_client(model_id)
        
        if okx_client:
            return self._get_okx_portfolio(model_id, okx_client, current_prices)
        else:
            return self._get_simulated_portfolio(model_id, current_prices)
    
    def _get_okx_portfolio(self, model_id: int, okx_client: 'OKXClient', current_prices: Dict = None) -> Dict:
        """Get portfolio data from OKX API"""
        cache_key = f'okx_portfolio_{model_id}'
        
        # Check cache
        if cache_key in self._okx_cache:
            if time.time() - self._okx_cache_time[cache_key] < self._okx_cache_duration:
                return self._okx_cache[cache_key]
        
        try:
            # Get account balance from OKX
            balance_data = okx_client.get_account_balance()
            
            # Get positions from OKX
            okx_positions = okx_client.get_positions()
            
            # Get initial capital from database
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT initial_capital FROM models WHERE id = ?', (model_id,))
            initial_capital = cursor.fetchone()['initial_capital']
            conn.close()
            
            # Convert OKX data to our format
            portfolio_data = self._convert_okx_to_portfolio_format(
                model_id, balance_data, okx_positions, initial_capital, current_prices
            )
            
            # Update cache
            self._okx_cache[cache_key] = portfolio_data
            self._okx_cache_time[cache_key] = time.time()
            
            return portfolio_data
            
        except Exception as e:
            print(f"[ERROR] Failed to get OKX portfolio data: {e}")
            # Fallback to simulated data
            return self._get_simulated_portfolio(model_id, current_prices)
    
    def _convert_okx_to_portfolio_format(self, model_id: int, balance_data: Dict, 
                                        okx_positions: List[Dict], initial_capital: float,
                                        current_prices: Dict = None) -> Dict:
        """Convert OKX API data to our portfolio format"""
        
        # Helper function to safely convert to float
        def safe_float(value, default=0):
            if value is None or value == '' or value == 'null':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        # Helper function to safely convert to int
        def safe_int(value, default=1):
            if value is None or value == '' or value == 'null':
                return default
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return default
        
        # OKX symbol to coin mapping (支持现货和永续合约)
        okx_to_coin = {
            # 现货交易对
            'BTC-USDT': 'BTC',
            'ETH-USDT': 'ETH', 
            'SOL-USDT': 'SOL',
            'BNB-USDT': 'BNB',
            'XRP-USDT': 'XRP',
            'DOGE-USDT': 'DOGE',
            # 永续合约
            'BTC-USDT-SWAP': 'BTC',
            'ETH-USDT-SWAP': 'ETH',
            'SOL-USDT-SWAP': 'SOL',
            'BNB-USDT-SWAP': 'BNB',
            'XRP-USDT-SWAP': 'XRP',
            'DOGE-USDT-SWAP': 'DOGE',
            # 期货合约 (如果需要)
            'BTC-USD-SWAP': 'BTC',
            'ETH-USD-SWAP': 'ETH'
        }
        
        # Convert positions
        positions = []
        total_unrealized_pnl = 0
        
        for okx_pos in okx_positions:
            symbol = okx_pos.get('symbol', '')
            coin = okx_to_coin.get(symbol)
            
            if coin:
                # Safely extract position data
                size = safe_float(okx_pos.get('size', 0))
                avg_price = safe_float(okx_pos.get('avg_price', 0))
                mark_price = safe_float(okx_pos.get('mark_price', avg_price))
                leverage = safe_int(okx_pos.get('leverage', 1))
                pnl = safe_float(okx_pos.get('unrealized_pnl', 0))
                margin = safe_float(okx_pos.get('margin', 0))
                
                position = {
                    'coin': coin,
                    'side': okx_pos.get('side', 'long'),
                    'quantity': size,
                    'avg_price': avg_price,
                    'current_price': mark_price,
                    'leverage': leverage,
                    'pnl': pnl,
                    'margin': margin
                }
                positions.append(position)
                total_unrealized_pnl += pnl
        
        # Calculate values safely
        total_equity = safe_float(balance_data.get('total_equity', initial_capital), initial_capital)
        available_balance = safe_float(balance_data.get('available_balance', 0))
        
        # Calculate realized P&L (total equity - initial capital - unrealized P&L)
        realized_pnl = total_equity - initial_capital - total_unrealized_pnl
        
        # Calculate position value and margin used
        positions_value = sum([safe_float(p['quantity']) * safe_float(p['avg_price']) for p in positions])
        margin_used = sum([safe_float(p.get('margin', 0)) for p in positions])
        
        return {
            'model_id': model_id,
            'initial_capital': initial_capital,
            'cash': available_balance,
            'positions': positions,
            'positions_value': positions_value,
            'margin_used': margin_used,
            'total_value': total_equity,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': total_unrealized_pnl
        }
    
    def _get_simulated_portfolio(self, model_id: int, current_prices: Dict = None) -> Dict:
        """Get simulated portfolio data (fallback)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get positions
        cursor.execute('''
            SELECT * FROM portfolios WHERE model_id = ? AND quantity > 0
        ''', (model_id,))
        positions = [dict(row) for row in cursor.fetchall()]
        
        # Get initial capital
        cursor.execute('SELECT initial_capital FROM models WHERE id = ?', (model_id,))
        initial_capital = cursor.fetchone()['initial_capital']
        
        # Calculate realized P&L (sum of all trade P&L)
        cursor.execute('''
            SELECT COALESCE(SUM(pnl), 0) as total_pnl FROM trades WHERE model_id = ?
        ''', (model_id,))
        realized_pnl = cursor.fetchone()['total_pnl']
        
        # Calculate margin used
        margin_used = sum([p['quantity'] * p['avg_price'] / p['leverage'] for p in positions])
        
        # Calculate unrealized P&L (if prices provided)
        unrealized_pnl = 0
        if current_prices:
            for pos in positions:
                coin = pos['coin']
                if coin in current_prices:
                    current_price = current_prices[coin]
                    entry_price = pos['avg_price']
                    quantity = pos['quantity']
                    
                    # Add current price to position
                    pos['current_price'] = current_price
                    
                    # Calculate position P&L
                    if pos['side'] == 'long':
                        pos_pnl = (current_price - entry_price) * quantity
                    else:  # short
                        pos_pnl = (entry_price - current_price) * quantity
                    
                    pos['pnl'] = pos_pnl
                    unrealized_pnl += pos_pnl
                else:
                    pos['current_price'] = None
                    pos['pnl'] = 0
        else:
            for pos in positions:
                pos['current_price'] = None
                pos['pnl'] = 0
        
        # Cash = initial capital + realized P&L - margin used
        cash = initial_capital + realized_pnl - margin_used
        
        # Position value = quantity * entry price (not margin!)
        positions_value = sum([p['quantity'] * p['avg_price'] for p in positions])
        
        # Total account value = initial capital + realized P&L + unrealized P&L
        total_value = initial_capital + realized_pnl + unrealized_pnl
        
        conn.close()
        
        return {
            'model_id': model_id,
            'cash': cash,
            'positions': positions,
            'positions_value': positions_value,
            'margin_used': margin_used,
            'total_value': total_value,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl
        }
    
    def close_position(self, model_id: int, coin: str, side: str = 'long'):
        """Close position"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM portfolios WHERE model_id = ? AND coin = ? AND side = ?
        ''', (model_id, coin, side))
        conn.commit()
        conn.close()
    
    # ============ Trade Records ============
    
    def add_trade(self, model_id: int, coin: str, signal: str, quantity: float,
                  price: float, leverage: int = 1, side: str = 'long', pnl: float = 0):
        """Add trade record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (model_id, coin, signal, quantity, price, leverage, side, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (model_id, coin, signal, quantity, price, leverage, side, pnl))
        conn.commit()
        conn.close()
    
    def get_trades(self, model_id: int, limit: int = 50) -> List[Dict]:
        """Get trade history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM trades WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ============ Conversation History ============
    
    def add_conversation(self, model_id: int, user_prompt: str, 
                        ai_response: str, cot_trace: str = ''):
        """Add conversation record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (model_id, user_prompt, ai_response, cot_trace)
            VALUES (?, ?, ?, ?)
        ''', (model_id, user_prompt, ai_response, cot_trace))
        conn.commit()
        conn.close()
    
    def get_conversations(self, model_id: int, limit: int = 20) -> List[Dict]:
        """Get conversation history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM conversations WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    # ============ Account Value History ============
    
    def record_account_value(self, model_id: int, total_value: float, 
                            cash: float, positions_value: float):
        """Record account value snapshot"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO account_values (model_id, total_value, cash, positions_value)
            VALUES (?, ?, ?, ?)
        ''', (model_id, total_value, cash, positions_value))
        conn.commit()
        conn.close()
    
    def get_account_value_history(self, model_id: int, limit: int = 100) -> List[Dict]:
        """Get account value history"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM account_values WHERE model_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (model_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

