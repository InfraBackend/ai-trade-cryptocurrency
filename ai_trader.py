import json
from typing import Dict

class AITrader:
    def __init__(self, api_key: str, api_url: str, model_name: str, system_prompt: str = ''):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.system_prompt = system_prompt
    
    def make_decision(self, market_state: Dict, portfolio: Dict, 
                     account_info: Dict) -> Dict:
        try:
            prompt = self._build_prompt(market_state, portfolio, account_info)
            response = self._call_llm(prompt)
            decisions = self._parse_response(response)
            
            # Validate decisions format
            if not decisions or not isinstance(decisions, dict):
                print("[WARNING] Invalid AI response format, using default hold strategy")
                return self._get_default_decisions(market_state)
            
            return decisions
            
        except Exception as e:
            print(f"[WARNING] AI decision failed: {e}")
            return self._get_default_decisions(market_state)
    
    def _get_default_decisions(self, market_state: Dict) -> Dict:
        """Generate default hold decisions when AI is unavailable"""
        decisions = {}
        for coin in market_state.keys():
            decisions[coin] = {
                'signal': 'hold',
                'quantity': 0,
                'leverage': 1,
                'confidence': 0.5,
                'justification': 'AI unavailable - default hold strategy'
            }
        return decisions
    
    def _build_prompt(self, market_state: Dict, portfolio: Dict, 
                     account_info: Dict) -> str:
        # Use custom system prompt if provided, otherwise use default
        if self.system_prompt.strip():
            system_role = self.system_prompt.strip()
        else:
            system_role = "You are a professional cryptocurrency trader. Analyze the market and make trading decisions."
        
        prompt = f"""{system_role}

MARKET DATA:
"""
        for coin, data in market_state.items():
            prompt += f"{coin}: ${data['price']:.2f} ({data['change_24h']:+.2f}%)\n"
            if 'indicators' in data and data['indicators']:
                indicators = data['indicators']
                prompt += f"  SMA7: ${indicators.get('sma_7', 0):.2f}, SMA14: ${indicators.get('sma_14', 0):.2f}, RSI: {indicators.get('rsi_14', 0):.1f}\n"
        
        prompt += f"""
ACCOUNT STATUS:
- Initial Capital: ${account_info['initial_capital']:.2f}
- Total Value: ${portfolio['total_value']:.2f}
- Cash: ${portfolio['cash']:.2f}
- Total Return: {account_info['total_return']:.2f}%

CURRENT POSITIONS:
"""
        if portfolio['positions']:
            for pos in portfolio['positions']:
                prompt += f"- {pos['coin']} {pos['side']}: {pos['quantity']:.4f} @ ${pos['avg_price']:.2f} ({pos['leverage']}x)\n"
        else:
            prompt += "None\n"
        
        prompt += """
TRADING RULES:
1. Signals: buy_to_enter (long), sell_to_enter (short), close_position, hold
2. Risk Management:
   - Max 3 positions
   - Risk 1-5% per trade
   - Use appropriate leverage (1-20x)
3. Position Sizing:
   - Conservative: 1-2% risk
   - Moderate: 2-4% risk
   - Aggressive: 4-5% risk
4. Exit Strategy:
   - Close losing positions quickly
   - Let winners run
   - Use technical indicators

OUTPUT FORMAT (JSON only):
```json
{
  "COIN": {
    "signal": "buy_to_enter|sell_to_enter|hold|close_position",
    "quantity": 0.5,
    "leverage": 10,
    "profit_target": 45000.0,
    "stop_loss": 42000.0,
    "confidence": 0.75,
    "justification": "Brief reason"
  }
}
```

Analyze and output JSON only.
"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        try:
            # 使用requests直接调用API，完全绕过代理设置
            import requests
            import json
            import os
            
            # 临时保存并清除所有代理相关的环境变量
            proxy_vars = [
                'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'
            ]
            
            saved_proxies = {}
            for var in proxy_vars:
                if var in os.environ:
                    saved_proxies[var] = os.environ[var]
                    del os.environ[var]
            
            try:
                base_url = self.api_url.rstrip('/')
                if not base_url.endswith('/v1'):
                    if '/v1' in base_url:
                        base_url = base_url.split('/v1')[0] + '/v1'
                    else:
                        base_url = base_url + '/v1'
                
                api_url = f"{base_url}/chat/completions"
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': 'AI-Trading-Bot/1.0'
                }
                
                payload = {
                    "model": self.model_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a professional cryptocurrency trader. Output JSON format only."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                
                # 创建一个新的session，明确禁用代理
                session = requests.Session()
                session.proxies = {}  # 清空代理设置
                
                response = session.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result['choices'][0]['message']['content']
                else:
                    raise Exception(f"API request failed with status {response.status_code}: {response.text[:200]}")
                    
            finally:
                # 恢复代理环境变量
                for var, value in saved_proxies.items():
                    os.environ[var] = value
                
        except requests.exceptions.Timeout:
            raise Exception("API request timeout")
        except requests.exceptions.ConnectionError as e:
            raise Exception(f"API connection failed: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request error: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"API response parsing failed: {str(e)}")
        except KeyError as e:
            raise Exception(f"API response format error: missing {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error: {str(e)}")
            
        except Exception as e:
            # Handle different types of errors gracefully
            error_str = str(e).lower()
            if "timeout" in error_str or "timed out" in error_str:
                error_msg = f"API request timeout: {str(e)}"
                print(f"[WARNING] {error_msg}")
            elif "connection" in error_str:
                error_msg = f"Network connection failed: {str(e)}"
                print(f"[ERROR] {error_msg}")
            elif "status" in error_str and "403" in error_str:
                error_msg = f"API access forbidden (403): Check API key and permissions"
                print(f"[ERROR] {error_msg}")
            elif "status" in error_str and "401" in error_str:
                error_msg = f"API authentication failed (401): Invalid API key"
                print(f"[ERROR] {error_msg}")
            else:
                error_msg = f"LLM call failed: {str(e)}"
                print(f"[ERROR] {error_msg}")
            raise Exception(error_msg)
    
    def _parse_response(self, response: str) -> Dict:
        response = response.strip()
        
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            response = response.split('```')[1].split('```')[0]
        
        try:
            decisions = json.loads(response.strip())
            return decisions
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse failed: {e}")
            print(f"[DATA] Response:\n{response}")
            return {}
