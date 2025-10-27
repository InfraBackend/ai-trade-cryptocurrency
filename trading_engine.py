from datetime import datetime
from typing import Dict
import json

# Import OKX client (optional dependency)
try:
    from okx_client import OKXClient
    OKX_AVAILABLE = True
except ImportError:
    OKX_AVAILABLE = False
    print("[INFO] OKX client not available, using simulation mode")

# Import new modules
try:
    from risk_manager import RiskManager
    from enhanced_prompts import get_enhanced_trading_prompt
    from monitoring import get_monitor
    ENHANCED_FEATURES = True
except ImportError:
    ENHANCED_FEATURES = False
    print("[INFO] Enhanced features not available, using basic functionality")

class TradingEngine:
    def __init__(self, model_id: int, db, market_fetcher, ai_trader, okx_client=None):
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.okx_client = okx_client
        
        # Initialize enhanced features
        if ENHANCED_FEATURES:
            self.risk_manager = RiskManager(model_id, db)
            self.monitor = get_monitor(db)
        else:
            self.risk_manager = None
            self.monitor = None
        
        # Load model configuration
        model = self.db.get_model(model_id)
        if model:
            # Parse trading coins from configuration
            trading_coins_str = model.get('trading_coins', 'BTC,ETH,SOL,BNB,XRP,DOGE')
            self.coins = [coin.strip() for coin in trading_coins_str.split(',') if coin.strip()]
            self.auto_trading_enabled = model.get('auto_trading_enabled', True)
            self.system_prompt = model.get('system_prompt', '')
        else:
            # Fallback to default values
            self.coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
            self.auto_trading_enabled = True
            self.system_prompt = ''
        
        # OKX symbol mapping (使用永续合约以支持杠杆交易)
        self.okx_symbols = {
            'BTC': 'BTC-USDT-SWAP',
            'ETH': 'ETH-USDT-SWAP',
            'SOL': 'SOL-USDT-SWAP',
            'BNB': 'BNB-USDT-SWAP',
            'XRP': 'XRP-USDT-SWAP',
            'DOGE': 'DOGE-USDT-SWAP'
        }
    
    def execute_trading_cycle(self) -> Dict:
        try:
            market_state = self._get_market_state()
            
            current_prices = {coin: market_state[coin]['price'] for coin in market_state}
            
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            
            # 🚨 STEP 1: Check for stop loss and take profit triggers
            stop_loss_actions = []
            if ENHANCED_FEATURES and self.risk_manager:
                stop_loss_actions = self.risk_manager.check_stop_loss_take_profit(portfolio, current_prices)
                
                # Execute stop loss/take profit actions immediately
                if stop_loss_actions:
                    print(f"[RISK] Model {self.model_id}: Executing {len(stop_loss_actions)} stop loss/take profit actions")
                    for action in stop_loss_actions:
                        try:
                            result = self._execute_stop_loss_take_profit(action, current_prices)
                            if self.monitor:
                                self.monitor.log_trading_event(
                                    self.model_id, 
                                    'stop_loss_executed' if action['action'] == 'stop_loss' else 'take_profit_executed',
                                    {
                                        'coin': action['coin'],
                                        'reason': action['reason'],
                                        'quantity': action['quantity'],
                                        'result': result
                                    }
                                )
                        except Exception as e:
                            print(f"[ERROR] Failed to execute {action['action']} for {action['coin']}: {e}")
                            if self.monitor:
                                self.monitor.log_trading_event(self.model_id, 'stop_loss_error', {
                                    'coin': action['coin'],
                                    'error': str(e)
                                })
            
            # Refresh portfolio after stop loss/take profit execution
            if stop_loss_actions:
                portfolio = self.db.get_portfolio(self.model_id, current_prices)
            
            account_info = self._build_account_info(portfolio)
            
            # 🤖 STEP 2: Get AI trading decisions
            decisions = self.ai_trader.make_decision(
                market_state, portfolio, account_info
            )
            
            self.db.add_conversation(
                self.model_id,
                user_prompt=self._format_prompt(market_state, portfolio, account_info),
                ai_response=json.dumps(decisions, ensure_ascii=False),
                cot_trace=''
            )
            
            # 🎯 STEP 3: Execute AI trading decisions (with risk validation)
            execution_results = self._execute_decisions(decisions, market_state, portfolio)
            
            # 📊 STEP 4: Update portfolio and record metrics
            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            self.db.record_account_value(
                self.model_id,
                updated_portfolio['total_value'],
                updated_portfolio['cash'],
                updated_portfolio['positions_value']
            )
            
            return {
                'success': True,
                'decisions': decisions,
                'executions': execution_results,
                'stop_loss_actions': stop_loss_actions,
                'portfolio': updated_portfolio
            }
            
        except Exception as e:
            print(f"[ERROR] Trading cycle failed (Model {self.model_id}): {e}")
            import traceback
            print(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_market_state(self) -> Dict:
        market_state = {}
        prices = self.market_fetcher.get_current_prices(self.coins)
        
        for coin in self.coins:
            if coin in prices:
                market_state[coin] = prices[coin].copy()
                indicators = self.market_fetcher.calculate_technical_indicators(coin)
                market_state[coin]['indicators'] = indicators
        
        return market_state
    
    def _execute_stop_loss_take_profit(self, action: Dict, current_prices: Dict) -> Dict:
        """Execute stop loss or take profit action"""
        coin = action['coin']
        quantity = action['quantity']
        side = action['side']  # 'sell' for closing long, 'buy' for closing short
        action_type = action['action']  # 'stop_loss' or 'take_profit'
        
        print(f"[{action_type.upper()}] {coin}: {action['reason']}")
        
        try:
            if self.okx_client:
                # Execute on OKX
                symbol = self.okx_symbols.get(coin)
                if symbol:
                    order_result = self.okx_client.place_order(
                        symbol=symbol,
                        side=side,
                        amount=quantity,
                        order_type='market'
                    )
                    
                    if order_result['success']:
                        # Record the trade
                        current_price = current_prices.get(coin, 0)
                        self.db.add_trade(
                            self.model_id, coin, 'close_position', quantity,
                            current_price, 1, action_type, pnl=0  # PnL will be calculated
                        )
                        
                        return {
                            'success': True,
                            'method': 'okx',
                            'order_id': order_result.get('order_id'),
                            'message': f'{action_type} executed on OKX'
                        }
                    else:
                        return {
                            'success': False,
                            'method': 'okx',
                            'error': order_result.get('message', 'Unknown error')
                        }
            
            # Fallback to simulation
            current_price = current_prices.get(coin, 0)
            
            # Calculate P&L for the closed position
            portfolio = self.db.get_portfolio(self.model_id, current_prices)
            position = None
            for pos in portfolio.get('positions', []):
                if pos['coin'] == coin:
                    position = pos
                    break
            
            pnl = 0
            if position:
                entry_price = position['avg_price']
                if position['side'] == 'long':
                    pnl = (current_price - entry_price) * quantity
                else:
                    pnl = (entry_price - current_price) * quantity
            
            # Close position in database
            self.db.close_position(self.model_id, coin, position['side'] if position else 'long')
            
            # Record the trade
            self.db.add_trade(
                self.model_id, coin, 'close_position', quantity,
                current_price, 1, action_type, pnl=pnl
            )
            
            return {
                'success': True,
                'method': 'simulation',
                'pnl': pnl,
                'message': f'{action_type} executed (simulation)'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'{action_type} execution failed'
            }
    
    def _build_account_info(self, portfolio: Dict) -> Dict:
        model = self.db.get_model(self.model_id)
        initial_capital = model['initial_capital']
        total_value = portfolio['total_value']
        total_return = ((total_value - initial_capital) / initial_capital) * 100
        
        return {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_return': total_return,
            'initial_capital': initial_capital
        }
    
    def _format_prompt(self, market_state: Dict, portfolio: Dict, 
                      account_info: Dict) -> str:
        return f"Market State: {len(market_state)} coins, Portfolio: {len(portfolio['positions'])} positions"
    
    def _execute_decisions(self, decisions: Dict, market_state: Dict, 
                          portfolio: Dict) -> list:
        results = []
        
        for coin, decision in decisions.items():
            if coin not in self.coins:
                continue
            
            signal = decision.get('signal', '').lower()
            
            try:
                if signal == 'buy_to_enter':
                    result = self._execute_buy(coin, decision, market_state, portfolio)
                elif signal == 'sell_to_enter':
                    result = self._execute_sell(coin, decision, market_state, portfolio)
                elif signal == 'close_position':
                    result = self._execute_close(coin, decision, market_state, portfolio)
                elif signal == 'hold':
                    result = {'coin': coin, 'signal': 'hold', 'message': 'Hold position'}
                else:
                    result = {'coin': coin, 'error': f'Unknown signal: {signal}'}
                
                results.append(result)
                
            except Exception as e:
                results.append({'coin': coin, 'error': str(e)})
        
        return results
    
    def _execute_buy(self, coin: str, decision: Dict, market_state: Dict, 
                    portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        leverage = int(decision.get('leverage', 1))
        price = market_state[coin]['price']
        
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity'}
        
        # 🛡️ Risk validation if enhanced features available
        if ENHANCED_FEATURES and self.risk_manager:
            validation = self.risk_manager.validate_order(
                coin, 'buy', quantity, leverage, price, portfolio
            )
            
            if not validation['valid']:
                error_msg = f"Risk validation failed: {'; '.join(validation['errors'])}"
                print(f"[RISK] {error_msg}")
                if self.monitor:
                    self.monitor.log_trading_event(self.model_id, 'risk_violation', {
                        'coin': coin,
                        'message': error_msg,
                        'errors': validation['errors']
                    })
                return {'coin': coin, 'error': error_msg}
            
            # Apply risk adjustments
            if validation['warnings']:
                print(f"[RISK] Adjustments applied: {'; '.join(validation['warnings'])}")
                quantity = validation['adjusted_quantity']
                leverage = validation['adjusted_leverage']
        
        # Use OKX API if available, otherwise fallback to simulation
        if self.okx_client:
            return self._execute_okx_buy(coin, quantity, leverage, price)
        else:
            return self._execute_simulated_buy(coin, quantity, leverage, price, portfolio)
    
    def _execute_okx_buy(self, coin: str, quantity: float, leverage: int, price: float) -> Dict:
        """Execute buy order via OKX API"""
        try:
            symbol = self.okx_symbols.get(coin)
            if not symbol:
                return {'coin': coin, 'error': f'Unsupported coin: {coin}'}
            
            # Check account config for debugging (first time only)
            if not hasattr(self, '_config_checked'):
                self.okx_client.get_account_config()
                self._config_checked = True
            
            # Place market order on OKX
            order_result = self.okx_client.place_order(
                symbol=symbol,
                side='buy',
                amount=quantity,
                order_type='market',
                leverage=leverage
            )
            
            if order_result['success']:
                # Record trade in database
                self.db.add_trade(
                    self.model_id, coin, 'buy_to_enter', quantity,
                    price, leverage, 'long', pnl=0
                )
                
                return {
                    'coin': coin,
                    'signal': 'buy_to_enter',
                    'quantity': quantity,
                    'price': price,
                    'leverage': leverage,
                    'order_id': order_result.get('order_id'),
                    'message': f'OKX Long {quantity:.4f} {coin} @ Market Price'
                }
            else:
                return {
                    'coin': coin,
                    'error': f'OKX order failed: {order_result.get("message", "Unknown error")}'
                }
                
        except Exception as e:
            return {'coin': coin, 'error': f'OKX API error: {str(e)}'}
    
    def _execute_simulated_buy(self, coin: str, quantity: float, leverage: int, 
                              price: float, portfolio: Dict) -> Dict:
        """Execute simulated buy order (fallback)"""
        required_margin = (quantity * price) / leverage
        if required_margin > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash'}
        
        self.db.update_position(
            self.model_id, coin, quantity, price, leverage, 'long'
        )
        
        self.db.add_trade(
            self.model_id, coin, 'buy_to_enter', quantity, 
            price, leverage, 'long', pnl=0
        )
        
        return {
            'coin': coin,
            'signal': 'buy_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'message': f'Simulated Long {quantity:.4f} {coin} @ ${price:.2f}'
        }
    
    def _execute_sell(self, coin: str, decision: Dict, market_state: Dict, 
                     portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        leverage = int(decision.get('leverage', 1))
        price = market_state[coin]['price']
        
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity'}
        
        # 🛡️ Risk validation if enhanced features available
        if ENHANCED_FEATURES and self.risk_manager:
            validation = self.risk_manager.validate_order(
                coin, 'sell', quantity, leverage, price, portfolio
            )
            
            if not validation['valid']:
                error_msg = f"Risk validation failed: {'; '.join(validation['errors'])}"
                print(f"[RISK] {error_msg}")
                if self.monitor:
                    self.monitor.log_trading_event(self.model_id, 'risk_violation', {
                        'coin': coin,
                        'message': error_msg,
                        'errors': validation['errors']
                    })
                return {'coin': coin, 'error': error_msg}
            
            # Apply risk adjustments
            if validation['warnings']:
                print(f"[RISK] Adjustments applied: {'; '.join(validation['warnings'])}")
                quantity = validation['adjusted_quantity']
                leverage = validation['adjusted_leverage']
        
        # Use OKX API if available, otherwise fallback to simulation
        if self.okx_client:
            return self._execute_okx_sell(coin, quantity, leverage, price)
        else:
            return self._execute_simulated_sell(coin, quantity, leverage, price, portfolio)
    
    def _execute_okx_sell(self, coin: str, quantity: float, leverage: int, price: float) -> Dict:
        """Execute sell order via OKX API"""
        try:
            symbol = self.okx_symbols.get(coin)
            if not symbol:
                return {'coin': coin, 'error': f'Unsupported coin: {coin}'}
            
            # Check account config for debugging (first time only)
            if not hasattr(self, '_config_checked'):
                self.okx_client.get_account_config()
                self._config_checked = True
            
            # Place market sell order on OKX
            order_result = self.okx_client.place_order(
                symbol=symbol,
                side='sell',
                amount=quantity,
                order_type='market',
                leverage=leverage
            )
            
            if order_result['success']:
                # Record trade in database
                self.db.add_trade(
                    self.model_id, coin, 'sell_to_enter', quantity,
                    price, leverage, 'short', pnl=0
                )
                
                return {
                    'coin': coin,
                    'signal': 'sell_to_enter',
                    'quantity': quantity,
                    'price': price,
                    'leverage': leverage,
                    'order_id': order_result.get('order_id'),
                    'message': f'OKX Short {quantity:.4f} {coin} @ Market Price'
                }
            else:
                return {
                    'coin': coin,
                    'error': f'OKX order failed: {order_result.get("message", "Unknown error")}'
                }
                
        except Exception as e:
            return {'coin': coin, 'error': f'OKX API error: {str(e)}'}
    
    def _execute_simulated_sell(self, coin: str, quantity: float, leverage: int, 
                               price: float, portfolio: Dict) -> Dict:
        """Execute simulated sell order (fallback)"""
        required_margin = (quantity * price) / leverage
        if required_margin > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash'}
        
        self.db.update_position(
            self.model_id, coin, quantity, price, leverage, 'short'
        )
        
        self.db.add_trade(
            self.model_id, coin, 'sell_to_enter', quantity, 
            price, leverage, 'short', pnl=0
        )
        
        return {
            'coin': coin,
            'signal': 'sell_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'message': f'Simulated Short {quantity:.4f} {coin} @ ${price:.2f}'
        }
    
    def _execute_close(self, coin: str, decision: Dict, market_state: Dict, 
                      portfolio: Dict) -> Dict:
        # Use OKX API if available, otherwise fallback to simulation
        if self.okx_client:
            return self._execute_okx_close(coin, market_state)
        else:
            return self._execute_simulated_close(coin, market_state, portfolio)
    
    def _execute_okx_close(self, coin: str, market_state: Dict) -> Dict:
        """Execute close position via OKX API"""
        try:
            symbol = self.okx_symbols.get(coin)
            if not symbol:
                return {'coin': coin, 'error': f'Unsupported coin: {coin}'}
            
            # Close position on OKX
            close_result = self.okx_client.close_position(symbol=symbol)
            
            if close_result['success']:
                current_price = market_state[coin]['price']
                
                # Record trade in database
                self.db.add_trade(
                    self.model_id, coin, 'close_position', 0,  # Quantity will be updated from OKX
                    current_price, 1, 'close', pnl=0  # PnL will be updated from OKX
                )
                
                return {
                    'coin': coin,
                    'signal': 'close_position',
                    'quantity': 0,  # Will be updated from OKX position data
                    'price': current_price,
                    'pnl': 0,  # Will be updated from OKX
                    'order_id': close_result.get('order_id'),
                    'message': f'OKX Close {coin} position'
                }
            else:
                return {
                    'coin': coin,
                    'error': f'OKX close failed: {close_result.get("message", "Unknown error")}'
                }
                
        except Exception as e:
            return {'coin': coin, 'error': f'OKX API error: {str(e)}'}
    
    def _execute_simulated_close(self, coin: str, market_state: Dict, portfolio: Dict) -> Dict:
        """Execute simulated close position (fallback)"""
        position = None
        for pos in portfolio['positions']:
            if pos['coin'] == coin:
                position = pos
                break
        
        if not position:
            return {'coin': coin, 'error': 'Position not found'}
        
        current_price = market_state[coin]['price']
        entry_price = position['avg_price']
        quantity = position['quantity']
        side = position['side']
        
        if side == 'long':
            pnl = (current_price - entry_price) * quantity
        else:
            pnl = (entry_price - current_price) * quantity
        
        self.db.close_position(self.model_id, coin, side)
        
        self.db.add_trade(
            self.model_id, coin, 'close_position', quantity,
            current_price, position['leverage'], side, pnl=pnl
        )
        
        return {
            'coin': coin,
            'signal': 'close_position',
            'quantity': quantity,
            'price': current_price,
            'pnl': pnl,
            'message': f'Simulated Close {coin}, P&L: ${pnl:.2f}'
        }
