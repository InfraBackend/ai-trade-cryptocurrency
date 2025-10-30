from datetime import datetime
from typing import Dict
import json
import time

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
            print(f"[INFO] Risk management enabled for model {model_id}")
        else:
            self.risk_manager = None
            self.monitor = None
            print(f"[INFO] Enhanced features not available for model {model_id}")
        
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

            # 🔄 STEP 0: Sync positions with exchange (before any operations)
            # 确保数据库持仓与OKX实际持仓一致
            if self.okx_client:
                self.sync_positions_with_exchange()

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
        side = action['side']  # 'sell' for closing long, 'buy' for closing short
        action_type = action['action']  # 'stop_loss' or 'take_profit'
        
        print(f"[{action_type.upper()}] {coin}: {action['reason']}")
        
        try:
            if self.okx_client:
                # Get actual position from OKX before closing
                symbol = self.okx_symbols.get(coin)
                if not symbol:
                    return {'success': False, 'error': f'Unsupported coin: {coin}'}
                
                # Find the actual position
                positions = self.okx_client.get_positions()
                target_position = None
                for pos in positions:
                    if pos['symbol'] == symbol and abs(float(pos.get('size', 0))) > 0:
                        target_position = pos
                        break
                
                if not target_position:
                    # Position already closed or doesn't exist
                    print(f"[{action_type.upper()}] No active position found for {coin}")
                    return {
                        'success': False,
                        'error': f'No active position found for {coin}'
                    }
                
                # Get actual quantity from position
                actual_quantity = abs(float(target_position.get('size', 0)))
                
                # Execute close position instead of placing a separate order
                close_result = self.okx_client.close_position(symbol=symbol)

                if close_result['success']:
                    current_price = current_prices.get(coin, 0)
                    entry_price = float(target_position.get('avg_price', current_price))
                    position_side = target_position.get('side', 'long')

                    # Check if position was already closed
                    if close_result.get('already_closed'):
                        # Position already closed - just clean up database
                        self.db.close_position(self.model_id, coin, position_side)
                        print(f"[INFO] Cleaned up phantom position for {coin} - already closed on OKX")

                        return {
                            'success': True,
                            'method': 'okx',
                            'message': f'{action_type} - position already closed on OKX, database cleaned up'
                        }

                    # Position was actually closed now - calculate P&L
                    if position_side == 'long':
                        pnl = (current_price - entry_price) * actual_quantity
                    else:  # short position
                        pnl = (entry_price - current_price) * actual_quantity

                    # Close position in database
                    self.db.close_position(self.model_id, coin, position_side)

                    # Record the trade with actual values and correct side
                    self.db.add_trade(
                        self.model_id, coin, 'close_position', actual_quantity,
                        current_price, 1, position_side, pnl=pnl
                    )

                    return {
                        'success': True,
                        'method': 'okx',
                        'order_id': close_result.get('order_id'),
                        'message': f'{action_type} executed on OKX: {actual_quantity} {coin} @ ${current_price:.2f}, P&L: ${pnl:.2f}'
                    }
                else:
                    return {
                        'success': False,
                        'method': 'okx',
                        'error': close_result.get('message', 'Unknown error')
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
            quantity = action.get('quantity', 0)  # Get quantity from action
            position_side = 'long'  # Default side
            
            if position:
                entry_price = position['avg_price']
                position_side = position['side']
                quantity = position['quantity']  # Use actual position quantity
                
                if position_side == 'long':
                    pnl = (current_price - entry_price) * quantity
                else:
                    pnl = (entry_price - current_price) * quantity
            
            # Close position in database
            self.db.close_position(self.model_id, coin, position_side)
            
            # Record the trade with correct position side
            self.db.add_trade(
                self.model_id, coin, 'close_position', quantity,
                current_price, 1, position_side, pnl=pnl
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
    
    def sync_positions_with_exchange(self, force: bool = False):
        """
        完整的双向持仓同步机制

        处理三种情况：
        1. 幻影持仓：数据库有但OKX没有 → 清理数据库
        2. 反向幻影：OKX有但数据库没有 → 添加到数据库
        3. 数量不一致：更新数据库为OKX的实际数量

        Args:
            force: 强制同步，否则使用缓存（60秒内只同步一次）
        """
        if not self.okx_client:
            return

        # 同步频率控制（避免过于频繁）
        if not force:
            current_time = time.time()
            last_sync = getattr(self, '_last_sync_time', 0)
            if current_time - last_sync < 60:  # 60秒内不重复同步
                return
            self._last_sync_time = current_time

        try:
            print(f"\n{'='*60}")
            print(f"🔄 开始持仓同步检查 - 模型ID: {self.model_id}")
            print(f"{'='*60}")

            # 获取OKX实际持仓
            okx_positions = self.okx_client.get_positions()
            okx_active_positions = {}

            for pos in okx_positions:
                size = abs(float(pos.get('size', 0)))
                if size > 0:  # 只记录有持仓的
                    symbol = pos['symbol']
                    coin = symbol.replace('-USDT-SWAP', '')
                    okx_active_positions[coin] = pos
                    print(f"📍 OKX持仓: {coin} - {pos['side']} - 数量: {size}")

            # 获取数据库持仓
            portfolio = self.db.get_portfolio(self.model_id)
            db_positions = {pos['coin']: pos for pos in portfolio.get('positions', [])}

            if db_positions:
                print(f"\n📊 数据库持仓:")
                for coin, pos in db_positions.items():
                    print(f"  {coin} - {pos['side']} - 数量: {pos['quantity']}")
            else:
                print(f"\n📊 数据库无持仓")

            sync_actions = []

            # 1. 检查幻影持仓（数据库有但OKX没有）
            for coin, db_pos in db_positions.items():
                if coin not in okx_active_positions:
                    print(f"\n🧹 发现幻影持仓: {coin} ({db_pos['side']})")
                    print(f"   → 数据库显示数量: {db_pos['quantity']}")
                    print(f"   → OKX实际持仓: 无")
                    print(f"   → 操作: 清理数据库记录")

                    self.db.close_position(self.model_id, coin, db_pos['side'])
                    sync_actions.append(f"清理幻影持仓: {coin}")

            # 2. 检查反向幻影（OKX有但数据库没有）
            for coin, okx_pos in okx_active_positions.items():
                if coin not in db_positions:
                    print(f"\n🔍 发现反向幻影: {coin} ({okx_pos['side']})")
                    print(f"   → OKX实际持仓: {okx_pos['size']}")
                    print(f"   → 数据库记录: 无")
                    print(f"   → 操作: 添加到数据库")

                    # 添加到数据库
                    self.db.update_position(
                        self.model_id,
                        coin,
                        float(okx_pos['size']),
                        float(okx_pos['avg_price']),
                        int(float(okx_pos.get('leverage', 1))),
                        okx_pos['side']
                    )
                    sync_actions.append(f"添加反向幻影: {coin}")

                elif db_positions[coin]['side'] != okx_pos['side']:
                    # 持仓方向不一致（这种情况比较严重）
                    print(f"\n⚠️  持仓方向不一致: {coin}")
                    print(f"   → 数据库方向: {db_positions[coin]['side']}")
                    print(f"   → OKX方向: {okx_pos['side']}")
                    print(f"   → 操作: 以OKX为准，更新数据库")

                    # 先清理旧的
                    self.db.close_position(self.model_id, coin, db_positions[coin]['side'])
                    # 再添加新的
                    self.db.update_position(
                        self.model_id,
                        coin,
                        float(okx_pos['size']),
                        float(okx_pos['avg_price']),
                        int(float(okx_pos.get('leverage', 1))),
                        okx_pos['side']
                    )
                    sync_actions.append(f"修正方向不一致: {coin}")

            # 3. 检查数量不一致
            for coin in set(db_positions.keys()) & set(okx_active_positions.keys()):
                db_pos = db_positions[coin]
                okx_pos = okx_active_positions[coin]

                db_qty = float(db_pos['quantity'])
                okx_qty = float(okx_pos['size'])

                # 允许0.01%的误差
                if abs(db_qty - okx_qty) / max(db_qty, okx_qty) > 0.0001:
                    print(f"\n📐 数量不一致: {coin}")
                    print(f"   → 数据库数量: {db_qty}")
                    print(f"   → OKX数量: {okx_qty}")
                    print(f"   → 差异: {abs(db_qty - okx_qty)}")
                    print(f"   → 操作: 更新为OKX实际数量")

                    # 更新为OKX的实际数量
                    self.db.update_position(
                        self.model_id,
                        coin,
                        okx_qty,
                        float(okx_pos['avg_price']),
                        int(float(okx_pos.get('leverage', 1))),
                        okx_pos['side']
                    )
                    sync_actions.append(f"更新数量: {coin} ({db_qty:.4f} → {okx_qty:.4f})")

            # 同步总结
            print(f"\n{'='*60}")
            if sync_actions:
                print(f"✅ 同步完成，执行了 {len(sync_actions)} 个操作:")
                for action in sync_actions:
                    print(f"   • {action}")
            else:
                print(f"✅ 同步完成，数据库与OKX持仓完全一致")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ 持仓同步错误: {e}")
            import traceback
            traceback.print_exc()

    def _execute_close(self, coin: str, decision: Dict, market_state: Dict, 
                      portfolio: Dict) -> Dict:
        # Sync positions before closing to avoid phantom position issues
        if self.okx_client:
            self.sync_positions_with_exchange()
            return self._execute_okx_close(coin, market_state)
        else:
            return self._execute_simulated_close(coin, market_state, portfolio)
    
    def _execute_okx_close(self, coin: str, market_state: Dict) -> Dict:
        """Execute close position via OKX API"""
        try:
            symbol = self.okx_symbols.get(coin)
            if not symbol:
                return {'coin': coin, 'error': f'Unsupported coin: {coin}'}
            
            # Get current position before closing
            positions = self.okx_client.get_positions()
            target_position = None
            for pos in positions:
                if pos['symbol'] == symbol:
                    target_position = pos
                    break
            
            if not target_position:
                # Check if we have a phantom position in database that needs cleanup
                portfolio = self.db.get_portfolio(self.model_id)
                db_position = None
                for pos in portfolio.get('positions', []):
                    if pos['coin'] == coin:
                        db_position = pos
                        break
                
                if db_position:
                    # Clean up phantom position in database
                    self.db.close_position(self.model_id, coin, db_position['side'])
                    return {
                        'coin': coin,
                        'signal': 'close_position',
                        'quantity': 0,
                        'price': market_state[coin]['price'],
                        'pnl': 0,
                        'message': f'Cleaned up phantom position for {coin} (already closed on exchange)'
                    }
                
                return {'coin': coin, 'error': 'No position to close'}
            
            # Check if position is already closed (0 quantity)
            position_size = abs(float(target_position.get('size', 0)))
            if position_size == 0:
                # Position is already closed on OKX, clean up database
                portfolio = self.db.get_portfolio(self.model_id)
                for pos in portfolio.get('positions', []):
                    if pos['coin'] == coin:
                        self.db.close_position(self.model_id, coin, pos['side'])
                        break
                
                return {
                    'coin': coin,
                    'signal': 'close_position',
                    'quantity': 0,
                    'price': market_state[coin]['price'],
                    'pnl': 0,
                    'message': f'Position for {coin} already closed on exchange, database synced'
                }
            
            # Close position on OKX
            close_result = self.okx_client.close_position(symbol=symbol)

            if close_result['success']:
                current_price = market_state[coin]['price']
                position_side = target_position.get('side', 'long')

                # Check if position was already closed
                if close_result.get('already_closed'):
                    # Position already closed - just clean up database
                    self.db.close_position(self.model_id, coin, position_side)
                    print(f"[INFO] Cleaned up phantom position for {coin} - already closed on OKX")

                    return {
                        'coin': coin,
                        'signal': 'close_position',
                        'quantity': 0,
                        'price': current_price,
                        'pnl': 0,
                        'message': f'Position for {coin} already closed on OKX, database cleaned up'
                    }

                # Position was actually closed now - calculate P&L
                closed_quantity = position_size
                entry_price = float(target_position.get('avg_price', current_price))

                # Calculate P&L
                if position_side == 'long':
                    pnl = (current_price - entry_price) * closed_quantity
                else:
                    pnl = (entry_price - current_price) * closed_quantity

                # Close position in database
                self.db.close_position(self.model_id, coin, position_side)

                # Record trade in database with actual values
                self.db.add_trade(
                    self.model_id, coin, 'close_position', closed_quantity,
                    current_price, 1, position_side, pnl=pnl
                )

                return {
                    'coin': coin,
                    'signal': 'close_position',
                    'quantity': closed_quantity,
                    'price': current_price,
                    'pnl': pnl,
                    'order_id': close_result.get('order_id'),
                    'message': f'OKX Close {coin} position: {closed_quantity} @ ${current_price:.2f}, P&L: ${pnl:.2f}'
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
