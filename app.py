from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import time
import threading
from datetime import datetime

from trading_engine import TradingEngine
from market_data import MarketDataFetcher
from ai_trader import AITrader
from database import Database

# Import OKX client (optional dependency)
try:
    from okx_client import OKXClient
    OKX_AVAILABLE = True
except ImportError:
    OKX_AVAILABLE = False
    print("[INFO] OKX client not available")

app = Flask(__name__)
CORS(app)

db = Database('trading_bot.db')
market_fetcher = MarketDataFetcher()
trading_engines = {}
auto_trading = True

def validate_okx_config(data):
    """Validate OKX configuration"""
    try:
        okx_api_key = data.get('okx_api_key', '').strip()
        okx_secret_key = data.get('okx_secret_key', '').strip()
        okx_passphrase = data.get('okx_passphrase', '').strip()
        okx_sandbox_mode = data.get('okx_sandbox_mode', True)
        
        # Check if all required fields are provided
        if not all([okx_api_key, okx_secret_key, okx_passphrase]):
            return False, "All OKX fields (API key, secret key, passphrase) are required"
        
        # Basic format validation
        if len(okx_api_key) < 10:
            return False, "OKX API key too short"
        
        if len(okx_secret_key) < 10:
            return False, "OKX secret key too short"
        
        if len(okx_passphrase) < 1:
            return False, "OKX passphrase cannot be empty"
        
        # Test OKX connection with actual API call
        if OKX_AVAILABLE:
            try:
                print(f"[INFO] Testing OKX configuration...")
                test_client = OKXClient(
                    api_key=okx_api_key, 
                    secret_key=okx_secret_key, 
                    passphrase=okx_passphrase, 
                    sandbox=bool(okx_sandbox_mode)
                )
                
                # Test API call to verify credentials
                balance_data = test_client.get_account_balance()
                print(f"[INFO] OKX API test successful, total equity: {balance_data.get('total_equity', 0)}")
                return True, "OKX configuration validated successfully"
                
            except Exception as e:
                error_msg = str(e)
                print(f"[ERROR] OKX API test failed: {error_msg}")
                
                # Provide more specific error messages
                if "Invalid API credentials" in error_msg:
                    return False, "Invalid API credentials. Please check your API key, secret key, and passphrase."
                elif "Permission denied" in error_msg:
                    return False, "API key permissions insufficient. Please ensure your API key has trading permissions."
                elif "Auth" in error_msg or "authentication" in error_msg.lower():
                    return False, "Authentication failed. Please verify your API credentials and passphrase."
                else:
                    return False, f"OKX API connection failed: {error_msg}"
        else:
            return False, "OKX client not available. Please check if required dependencies are installed."
        
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def init_trading_engine_with_okx(model_id):
    """Initialize trading engine with OKX client if configured"""
    try:
        model = db.get_model(model_id)
        if not model:
            raise Exception(f"Model {model_id} not found")
        
        # Create OKX client if configured
        okx_client = None
        if OKX_AVAILABLE and all([model.get('okx_api_key'), model.get('okx_secret_key'), model.get('okx_passphrase')]):
            try:
                okx_client = OKXClient(
                    api_key=model['okx_api_key'],
                    secret_key=model['okx_secret_key'],
                    passphrase=model['okx_passphrase'],
                    sandbox=bool(model.get('okx_sandbox_mode', True))
                )
                print(f"[INFO] OKX client created for model {model_id}")
            except Exception as e:
                print(f"[WARNING] Failed to create OKX client for model {model_id}: {e}")
                okx_client = None
        
        # Create trading engine
        trading_engines[model_id] = TradingEngine(
            model_id=model_id,
            db=db,
            market_fetcher=market_fetcher,
            ai_trader=AITrader(
                api_key=model['api_key'],
                api_url=model['api_url'],
                model_name=model['model_name'],
                system_prompt=model.get('system_prompt', '')
            ),
            okx_client=okx_client
        )
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to initialize trading engine for model {model_id}: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/models', methods=['GET'])
def get_models():
    models = db.get_all_models()
    
    # Add OKX status information
    for model in models:
        # Check if OKX is configured
        has_okx_config = all([
            model.get('okx_api_key'), 
            model.get('okx_secret_key'), 
            model.get('okx_passphrase')
        ])
        
        # Check if it's test data
        is_test_config = False
        if has_okx_config:
            okx_fields = [model.get('okx_api_key', ''), model.get('okx_secret_key', ''), model.get('okx_passphrase', '')]
            is_test_config = any('test' in field.lower() for field in okx_fields if field)
        
        model['okx_status'] = 'configured' if has_okx_config and not is_test_config else 'not_configured'
        model['trading_mode'] = 'OKX' if has_okx_config and not is_test_config else 'Simulation'
    
    return jsonify(models)

@app.route('/api/models', methods=['POST'])
def add_model():
    data = request.json
    
    # Validate OKX configuration if provided
    okx_config_valid = True
    okx_error_message = None
    
    if data.get('okx_api_key') or data.get('okx_secret_key') or data.get('okx_passphrase'):
        okx_config_valid, okx_error_message = validate_okx_config(data)
        if not okx_config_valid:
            return jsonify({'error': f'OKX configuration invalid: {okx_error_message}'}), 400
    
    # Add model with OKX configuration and trading settings
    model_id = db.add_model(
        name=data['name'],
        api_key=data['api_key'],
        api_url=data['api_url'],
        model_name=data['model_name'],
        initial_capital=float(data.get('initial_capital', 100000)),
        okx_api_key=data.get('okx_api_key', ''),
        okx_secret_key=data.get('okx_secret_key', ''),
        okx_passphrase=data.get('okx_passphrase', ''),
        okx_sandbox_mode=bool(data.get('okx_sandbox_mode', True)),
        trading_frequency=int(data.get('trading_frequency', 180)),
        trading_coins=data.get('trading_coins', 'BTC,ETH,SOL,BNB,XRP,DOGE'),
        auto_trading_enabled=bool(data.get('auto_trading_enabled', True)),
        system_prompt=data.get('system_prompt', '')
    )
    
    try:
        # Initialize trading engine with OKX client
        init_trading_engine_with_okx(model_id)
        print(f"[INFO] Model {model_id} ({data['name']}) initialized with OKX: {okx_config_valid}")
    except Exception as e:
        print(f"[ERROR] Model {model_id} initialization failed: {e}")
    
    return jsonify({'id': model_id, 'message': 'Model added successfully'})

@app.route('/api/models/<int:model_id>', methods=['GET'])
def get_model(model_id):
    """Get single model information"""
    try:
        model = db.get_model(model_id)
        if not model:
            return jsonify({'error': 'Model not found'}), 404
        return jsonify(model)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>', methods=['PUT'])
def update_model(model_id):
    """Update existing model"""
    try:
        data = request.json
        
        # Validate required fields
        if not all([data.get('name'), data.get('api_key'), data.get('api_url'), data.get('model_name')]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Validate OKX configuration if provided
        okx_config_valid = True
        okx_error_message = None
        
        if data.get('okx_api_key') or data.get('okx_secret_key') or data.get('okx_passphrase'):
            okx_config_valid, okx_error_message = validate_okx_config(data)
            if not okx_config_valid:
                return jsonify({'error': f'OKX configuration invalid: {okx_error_message}'}), 400
        
        # Update model in database
        success = db.update_model(
            model_id=model_id,
            name=data['name'],
            api_key=data['api_key'],
            api_url=data['api_url'],
            model_name=data['model_name'],
            initial_capital=float(data.get('initial_capital', 100000)),
            okx_api_key=data.get('okx_api_key', ''),
            okx_secret_key=data.get('okx_secret_key', ''),
            okx_passphrase=data.get('okx_passphrase', ''),
            okx_sandbox_mode=bool(data.get('okx_sandbox_mode', True)),
            trading_frequency=int(data.get('trading_frequency', 180)),
            trading_coins=data.get('trading_coins', 'BTC,ETH,SOL,BNB,XRP,DOGE'),
            auto_trading_enabled=bool(data.get('auto_trading_enabled', True)),
            system_prompt=data.get('system_prompt', '')
        )
        
        if not success:
            return jsonify({'error': 'Model not found'}), 404
        
        # Restart trading engine if it was running
        if model_id in trading_engines:
            del trading_engines[model_id]
            init_trading_engine_with_okx(model_id)
        
        return jsonify({'message': 'Model updated successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>', methods=['DELETE'])
def delete_model(model_id):
    try:
        model = db.get_model(model_id)
        model_name = model['name'] if model else f"ID-{model_id}"
        
        db.delete_model(model_id)
        if model_id in trading_engines:
            del trading_engines[model_id]
        
        print(f"[INFO] Model {model_id} ({model_name}) deleted")
        return jsonify({'message': 'Model deleted successfully'})
    except Exception as e:
        print(f"[ERROR] Delete model {model_id} failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/portfolio', methods=['GET'])
def get_portfolio(model_id):
    prices_data = market_fetcher.get_current_prices(['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE'])
    current_prices = {coin: prices_data[coin]['price'] for coin in prices_data}
    
    portfolio = db.get_portfolio(model_id, current_prices)
    account_value = db.get_account_value_history(model_id, limit=100)
    
    return jsonify({
        'portfolio': portfolio,
        'account_value_history': account_value
    })

@app.route('/api/models/<int:model_id>/trades', methods=['GET'])
def get_trades(model_id):
    limit = request.args.get('limit', 50, type=int)
    trades = db.get_trades(model_id, limit=limit)
    return jsonify(trades)

@app.route('/api/models/<int:model_id>/conversations', methods=['GET'])
def get_conversations(model_id):
    limit = request.args.get('limit', 20, type=int)
    conversations = db.get_conversations(model_id, limit=limit)
    return jsonify(conversations)

@app.route('/api/market/prices', methods=['GET'])
def get_market_prices():
    coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
    prices = market_fetcher.get_current_prices(coins)
    return jsonify(prices)

@app.route('/api/okx/validate', methods=['POST'])
def validate_okx_configuration():
    """Validate OKX configuration"""
    try:
        data = request.json
        is_valid, error_message = validate_okx_config(data)
        
        if is_valid:
            return jsonify({'valid': True, 'message': 'OKX configuration is valid'})
        else:
            return jsonify({'valid': False, 'message': error_message}), 400
            
    except Exception as e:
        return jsonify({'valid': False, 'message': f'Validation error: {str(e)}'}), 500

@app.route('/api/models/<int:model_id>/execute', methods=['POST'])
def execute_trading(model_id):
    if model_id not in trading_engines:
        model = db.get_model(model_id)
        if not model:
            return jsonify({'error': 'Model not found'}), 404
        
        # Use the new initialization logic with OKX support
        if not init_trading_engine_with_okx(model_id):
            return jsonify({'error': 'Failed to initialize trading engine'}), 500
    
    try:
        result = trading_engines[model_id].execute_trading_cycle()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def trading_loop():
    print("[INFO] Trading loop started")
    
    # Track last execution time for each model
    last_execution = {}
    
    while auto_trading:
        try:
            if not trading_engines:
                time.sleep(30)
                continue
            
            current_time = time.time()
            executed_models = []
            
            for model_id, engine in list(trading_engines.items()):
                try:
                    # Get model configuration
                    model = db.get_model(model_id)
                    if not model:
                        continue
                    
                    # Check if auto trading is enabled for this model
                    if not model.get('auto_trading_enabled', True):
                        continue
                    
                    # Check if it's time to execute for this model
                    trading_frequency = model.get('trading_frequency', 180)  # seconds
                    last_exec_time = last_execution.get(model_id, 0)
                    
                    if current_time - last_exec_time >= trading_frequency:
                        print(f"\n[EXEC] Model {model_id} (frequency: {trading_frequency}s)")
                        result = engine.execute_trading_cycle()
                        
                        # Update last execution time
                        last_execution[model_id] = current_time
                        executed_models.append(model_id)
                        
                        if result.get('success'):
                            print(f"[OK] Model {model_id} completed")
                            if result.get('executions'):
                                for exec_result in result['executions']:
                                    signal = exec_result.get('signal', 'unknown')
                                    coin = exec_result.get('coin', 'unknown')
                                    msg = exec_result.get('message', '')
                                    if signal != 'hold':
                                        print(f"  [TRADE] {coin}: {msg}")
                        else:
                            error = result.get('error', 'Unknown error')
                            print(f"[WARN] Model {model_id} failed: {error}")
                        
                except Exception as e:
                    print(f"[ERROR] Model {model_id} exception: {e}")
                    import traceback
                    print(traceback.format_exc())
                    continue
            
            if executed_models:
                print(f"\n{'='*60}")
                print(f"[CYCLE] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"[INFO] Executed models: {executed_models}")
                print(f"{'='*60}")
            
            # Sleep for a short interval before checking again
            time.sleep(30)
            
        except Exception as e:
            print(f"\n[CRITICAL] Trading loop error: {e}")
            import traceback
            print(traceback.format_exc())
            print("[RETRY] Retrying in 60 seconds\n")
            time.sleep(60)
    
    print("[INFO] Trading loop stopped")

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    models = db.get_all_models()
    leaderboard = []
    
    prices_data = market_fetcher.get_current_prices(['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE'])
    current_prices = {coin: prices_data[coin]['price'] for coin in prices_data}
    
    for model in models:
        portfolio = db.get_portfolio(model['id'], current_prices)
        account_value = portfolio.get('total_value', model['initial_capital'])
        returns = ((account_value - model['initial_capital']) / model['initial_capital']) * 100
        
        leaderboard.append({
            'model_id': model['id'],
            'model_name': model['name'],
            'account_value': account_value,
            'returns': returns,
            'initial_capital': model['initial_capital']
        })
    
    leaderboard.sort(key=lambda x: x['returns'], reverse=True)
    return jsonify(leaderboard)

@app.route('/api/system/status', methods=['GET'])
def get_system_status():
    """Get comprehensive system status and health metrics"""
    try:
        # Import monitoring module
        from monitoring import get_monitor
        monitor = get_monitor(db)
        
        # Perform health check and get status
        status = monitor.get_system_status()
        
        # Add trading engines status
        status['trading_engines'] = {
            'active_count': len(trading_engines),
            'models': list(trading_engines.keys())
        }
        
        return jsonify(status)
        
    except ImportError:
        # Fallback if monitoring module not available
        return jsonify({
            'health_check': {
                'overall_status': 'basic',
                'message': 'Enhanced monitoring not available'
            },
            'trading_engines': {
                'active_count': len(trading_engines),
                'models': list(trading_engines.keys())
            },
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/models/<int:model_id>/risk-metrics', methods=['GET'])
def get_risk_metrics(model_id):
    """Get risk metrics for a specific model"""
    try:
        from risk_manager import RiskManager
        
        # Get current portfolio
        prices_data = market_fetcher.get_current_prices(['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE'])
        current_prices = {coin: prices_data[coin]['price'] for coin in prices_data}
        portfolio = db.get_portfolio(model_id, current_prices)
        
        # Get risk metrics
        risk_manager = RiskManager(model_id, db)
        metrics = risk_manager.get_risk_metrics(portfolio)
        
        return jsonify(metrics)
        
    except ImportError:
        return jsonify({'error': 'Risk management module not available'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def init_trading_engines():
    try:
        models = db.get_all_models()
        
        if not models:
            print("[WARN] No trading models found")
            return
        
        print(f"\n[INIT] Initializing trading engines...")
        for model in models:
            model_id = model['id']
            model_name = model['name']
            
            try:
                # Use the new initialization logic with OKX support
                if init_trading_engine_with_okx(model_id):
                    has_okx = bool(model.get('okx_api_key'))
                    print(f"  [OK] Model {model_id} ({model_name}) - OKX: {has_okx}")
                else:
                    print(f"  [ERROR] Model {model_id} ({model_name}): initialization failed")
                    continue
            except Exception as e:
                print(f"  [ERROR] Model {model_id} ({model_name}): {e}")
                continue
        
        print(f"[INFO] Initialized {len(trading_engines)} engine(s)\n")
        
    except Exception as e:
        print(f"[ERROR] Init engines failed: {e}\n")

if __name__ == '__main__':
    db.init_db()
    
    print("\n" + "=" * 60)
    print("AI Trading Platform")
    print("=" * 60)
    
    init_trading_engines()
    
    if auto_trading:
        trading_thread = threading.Thread(target=trading_loop, daemon=True)
        trading_thread.start()
        print("[INFO] Auto-trading enabled")
    
    print("\n" + "=" * 60)
    print("Server: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
