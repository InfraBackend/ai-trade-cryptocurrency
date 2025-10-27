"""
Risk Management Module for AI Trading System
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class RiskManager:
    """Comprehensive risk management for trading operations"""
    
    def __init__(self, model_id: int, db):
        self.model_id = model_id
        self.db = db
        
        # Risk parameters (can be made configurable)
        self.max_positions = 3
        self.max_risk_per_trade = 0.05  # 5% of account
        self.max_total_risk = 0.15      # 15% of account
        self.max_leverage = 20
        self.min_order_size = 10        # Minimum $10 order
        self.max_daily_trades = 10
        self.max_drawdown = 0.20        # 20% max drawdown
        
    def validate_order(self, coin: str, side: str, quantity: float, 
                      leverage: int, current_price: float, 
                      portfolio: Dict) -> Dict:
        """Comprehensive order validation"""
        
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'adjusted_quantity': quantity,
            'adjusted_leverage': leverage
        }
        
        try:
            # 1. Check position limits
            current_positions = len(portfolio.get('positions', []))
            if current_positions >= self.max_positions:
                validation_result['valid'] = False
                validation_result['errors'].append(f"Maximum positions limit reached ({self.max_positions})")
            
            # 2. Check leverage limits
            if leverage > self.max_leverage:
                validation_result['adjusted_leverage'] = self.max_leverage
                validation_result['warnings'].append(f"Leverage reduced from {leverage}x to {self.max_leverage}x")
            
            # 3. Check order size
            order_value = quantity * current_price
            if order_value < self.min_order_size:
                validation_result['valid'] = False
                validation_result['errors'].append(f"Order size too small (${order_value:.2f} < ${self.min_order_size})")
            
            # 4. Check risk per trade
            account_value = portfolio.get('total_value', 0)
            if account_value > 0:
                risk_amount = order_value / leverage  # Margin required
                risk_percentage = risk_amount / account_value
                
                if risk_percentage > self.max_risk_per_trade:
                    # Adjust quantity to meet risk limit
                    max_risk_amount = account_value * self.max_risk_per_trade
                    max_order_value = max_risk_amount * leverage
                    adjusted_quantity = max_order_value / current_price
                    
                    validation_result['adjusted_quantity'] = adjusted_quantity
                    validation_result['warnings'].append(
                        f"Quantity reduced from {quantity:.4f} to {adjusted_quantity:.4f} to meet risk limit"
                    )
            
            # 5. Check total portfolio risk
            total_risk = self._calculate_total_risk(portfolio)
            if total_risk > self.max_total_risk:
                validation_result['valid'] = False
                validation_result['errors'].append(f"Total portfolio risk too high ({total_risk:.1%} > {self.max_total_risk:.1%})")
            
            # 6. Check daily trade limit
            daily_trades = self._get_daily_trade_count()
            if daily_trades >= self.max_daily_trades:
                validation_result['valid'] = False
                validation_result['errors'].append(f"Daily trade limit reached ({daily_trades}/{self.max_daily_trades})")
            
            # 7. Check drawdown
            drawdown = self._calculate_drawdown(portfolio)
            if drawdown > self.max_drawdown:
                validation_result['valid'] = False
                validation_result['errors'].append(f"Maximum drawdown exceeded ({drawdown:.1%} > {self.max_drawdown:.1%})")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Risk validation error: {e}")
            return {
                'valid': False,
                'errors': [f"Risk validation failed: {str(e)}"],
                'warnings': [],
                'adjusted_quantity': quantity,
                'adjusted_leverage': leverage
            }
    
    def check_stop_loss_take_profit(self, portfolio: Dict, current_prices: Dict) -> List[Dict]:
        """Check if any positions need stop loss or take profit execution"""
        actions = []
        
        for position in portfolio.get('positions', []):
            coin = position['coin']
            if coin not in current_prices:
                continue
                
            current_price = current_prices[coin]
            entry_price = position['avg_price']
            side = position['side']
            quantity = position['quantity']
            
            # Calculate P&L percentage
            if side == 'long':
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            
            # Check stop loss (5% loss)
            if pnl_pct <= -0.05:
                actions.append({
                    'action': 'stop_loss',
                    'coin': coin,
                    'reason': f'Stop loss triggered: {pnl_pct:.1%} loss',
                    'quantity': quantity,
                    'side': 'sell' if side == 'long' else 'buy'
                })
            
            # Check take profit (15% gain)
            elif pnl_pct >= 0.15:
                actions.append({
                    'action': 'take_profit',
                    'coin': coin,
                    'reason': f'Take profit triggered: {pnl_pct:.1%} gain',
                    'quantity': quantity,
                    'side': 'sell' if side == 'long' else 'buy'
                })
        
        return actions
    
    def _calculate_total_risk(self, portfolio: Dict) -> float:
        """Calculate total portfolio risk exposure"""
        total_margin = 0
        account_value = portfolio.get('total_value', 0)
        
        for position in portfolio.get('positions', []):
            position_value = position['quantity'] * position['avg_price']
            margin = position_value / position.get('leverage', 1)
            total_margin += margin
        
        return total_margin / account_value if account_value > 0 else 0
    
    def _get_daily_trade_count(self) -> int:
        """Get number of trades executed today"""
        try:
            today = datetime.now().date()
            trades = self.db.get_trades(self.model_id, limit=100)
            
            daily_count = 0
            for trade in trades:
                trade_date = datetime.fromisoformat(trade['timestamp']).date()
                if trade_date == today:
                    daily_count += 1
                else:
                    break  # Trades are ordered by timestamp desc
            
            return daily_count
        except Exception as e:
            logger.error(f"Error getting daily trade count: {e}")
            return 0
    
    def _calculate_drawdown(self, portfolio: Dict) -> float:
        """Calculate current drawdown from peak"""
        try:
            model = self.db.get_model(self.model_id)
            if not model:
                return 0
            
            initial_capital = model['initial_capital']
            current_value = portfolio.get('total_value', initial_capital)
            
            # Get account value history to find peak
            history = self.db.get_account_value_history(self.model_id, limit=100)
            if not history:
                return 0
            
            peak_value = max([h['total_value'] for h in history] + [initial_capital])
            drawdown = (peak_value - current_value) / peak_value
            
            return max(0, drawdown)
        except Exception as e:
            logger.error(f"Error calculating drawdown: {e}")
            return 0
    
    def get_risk_metrics(self, portfolio: Dict) -> Dict:
        """Get comprehensive risk metrics"""
        return {
            'total_risk': self._calculate_total_risk(portfolio),
            'current_positions': len(portfolio.get('positions', [])),
            'max_positions': self.max_positions,
            'daily_trades': self._get_daily_trade_count(),
            'max_daily_trades': self.max_daily_trades,
            'drawdown': self._calculate_drawdown(portfolio),
            'max_drawdown': self.max_drawdown,
            'risk_status': 'healthy' if self._calculate_total_risk(portfolio) < self.max_total_risk else 'high_risk'
        }