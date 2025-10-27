"""
Monitoring and Alerting System for AI Trading Platform
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_system.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class TradingMonitor:
    """Comprehensive monitoring and alerting system"""
    
    def __init__(self, db):
        self.db = db
        self.alerts = []
        self.performance_metrics = {}
        self.last_health_check = None
        
    def log_trading_event(self, model_id: int, event_type: str, data: Dict):
        """Log structured trading events"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'model_id': model_id,
            'event_type': event_type,
            'data': data
        }
        
        logger.info(f"TRADING_EVENT: {json.dumps(event)}")
        
        # Check for alert conditions
        self._check_alert_conditions(model_id, event_type, data)
    
    def _check_alert_conditions(self, model_id: int, event_type: str, data: Dict):
        """Check if event triggers any alerts"""
        
        if event_type == 'trade_executed':
            # Alert on large losses
            pnl = data.get('pnl', 0)
            if pnl < -1000:  # Loss > $1000
                self._create_alert('large_loss', f"Model {model_id}: Large loss ${pnl:.2f}", 'high')
            
            # Alert on high leverage
            leverage = data.get('leverage', 1)
            if leverage > 15:
                self._create_alert('high_leverage', f"Model {model_id}: High leverage {leverage}x used", 'medium')
        
        elif event_type == 'api_error':
            error_msg = data.get('error', '')
            if 'authentication' in error_msg.lower():
                self._create_alert('auth_error', f"Model {model_id}: API authentication failed", 'high')
            else:
                self._create_alert('api_error', f"Model {model_id}: API error - {error_msg}", 'medium')
        
        elif event_type == 'risk_violation':
            self._create_alert('risk_violation', f"Model {model_id}: {data.get('message', 'Risk limit exceeded')}", 'high')
    
    def _create_alert(self, alert_type: str, message: str, severity: str):
        """Create and log alert"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'type': alert_type,
            'message': message,
            'severity': severity,
            'acknowledged': False
        }
        
        self.alerts.append(alert)
        
        # Log alert
        logger.warning(f"ALERT [{severity.upper()}]: {message}")
        
        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
    
    def perform_health_check(self) -> Dict:
        """Perform comprehensive system health check"""
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'checks': {}
        }
        
        try:
            # Check database connectivity
            models = self.db.get_all_models()
            health_status['checks']['database'] = {
                'status': 'healthy',
                'models_count': len(models),
                'message': f"Database accessible, {len(models)} models configured"
            }
        except Exception as e:
            health_status['checks']['database'] = {
                'status': 'unhealthy',
                'error': str(e),
                'message': "Database connection failed"
            }
            health_status['overall_status'] = 'unhealthy'
        
        # Check recent trading activity
        try:
            recent_trades = 0
            for model in models:
                trades = self.db.get_trades(model['id'], limit=10)
                recent_trades += len([t for t in trades if 
                    datetime.fromisoformat(t['timestamp']) > datetime.now() - timedelta(hours=24)])
            
            health_status['checks']['trading_activity'] = {
                'status': 'healthy' if recent_trades > 0 else 'warning',
                'recent_trades_24h': recent_trades,
                'message': f"{recent_trades} trades in last 24 hours"
            }
        except Exception as e:
            health_status['checks']['trading_activity'] = {
                'status': 'error',
                'error': str(e),
                'message': "Failed to check trading activity"
            }
        
        # Check for critical alerts
        critical_alerts = [a for a in self.alerts if a['severity'] == 'high' and not a['acknowledged']]
        health_status['checks']['alerts'] = {
            'status': 'healthy' if len(critical_alerts) == 0 else 'warning',
            'critical_alerts_count': len(critical_alerts),
            'total_alerts_count': len(self.alerts),
            'message': f"{len(critical_alerts)} critical alerts pending"
        }
        
        # Update overall status
        if any(check['status'] == 'unhealthy' for check in health_status['checks'].values()):
            health_status['overall_status'] = 'unhealthy'
        elif any(check['status'] in ['warning', 'error'] for check in health_status['checks'].values()):
            health_status['overall_status'] = 'warning'
        
        self.last_health_check = health_status
        logger.info(f"HEALTH_CHECK: {json.dumps(health_status)}")
        
        return health_status
    
    def get_performance_metrics(self, model_id: int) -> Dict:
        """Calculate comprehensive performance metrics"""
        try:
            model = self.db.get_model(model_id)
            if not model:
                return {}
            
            # Get account value history
            history = self.db.get_account_value_history(model_id, limit=100)
            if not history:
                return {}
            
            initial_capital = model['initial_capital']
            current_value = history[0]['total_value'] if history else initial_capital
            
            # Calculate metrics
            total_return = ((current_value - initial_capital) / initial_capital) * 100
            
            # Calculate max drawdown
            peak_value = initial_capital
            max_drawdown = 0
            for record in reversed(history):
                value = record['total_value']
                if value > peak_value:
                    peak_value = value
                drawdown = (peak_value - value) / peak_value
                max_drawdown = max(max_drawdown, drawdown)
            
            # Get trade statistics
            trades = self.db.get_trades(model_id, limit=100)
            winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
            
            win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
            avg_win = sum(t['pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t['pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            metrics = {
                'model_id': model_id,
                'total_return': total_return,
                'current_value': current_value,
                'initial_capital': initial_capital,
                'max_drawdown': max_drawdown * 100,
                'total_trades': len(trades),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0,
                'last_updated': datetime.now().isoformat()
            }
            
            self.performance_metrics[model_id] = metrics
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics for model {model_id}: {e}")
            return {}
    
    def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        return {
            'health_check': self.last_health_check or self.perform_health_check(),
            'active_alerts': [a for a in self.alerts if not a['acknowledged']],
            'performance_metrics': self.performance_metrics,
            'system_uptime': self._get_uptime(),
            'last_updated': datetime.now().isoformat()
        }
    
    def _get_uptime(self) -> str:
        """Get system uptime (simplified)"""
        # This is a simplified implementation
        # In production, you'd track actual start time
        return "System monitoring active"
    
    def acknowledge_alert(self, alert_index: int):
        """Acknowledge an alert"""
        if 0 <= alert_index < len(self.alerts):
            self.alerts[alert_index]['acknowledged'] = True
            logger.info(f"Alert acknowledged: {self.alerts[alert_index]['message']}")
    
    def clear_old_alerts(self, days: int = 7):
        """Clear alerts older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        self.alerts = [
            alert for alert in self.alerts 
            if datetime.fromisoformat(alert['timestamp']) > cutoff_date
        ]
        logger.info(f"Cleared alerts older than {days} days")

# Global monitor instance
monitor = None

def get_monitor(db):
    """Get global monitor instance"""
    global monitor
    if monitor is None:
        monitor = TradingMonitor(db)
    return monitor