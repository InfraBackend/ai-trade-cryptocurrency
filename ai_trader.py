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
        """生成AI交易决策，带改进的错误处理和日志"""
        import time
        
        start_time = time.time()
        
        try:
            print(f"[INFO] 开始AI决策生成 (市场数据: {len(market_state)}个币种)")
            
            prompt = self._build_prompt(market_state, portfolio, account_info)
            print(f"[INFO] 提示词构建完成 (长度: {len(prompt)}字符)")
            
            response = self._call_llm(prompt)
            print(f"[INFO] AI响应获取成功 (长度: {len(response)}字符)")
            
            decisions = self._parse_response(response)
            
            # Validate decisions format
            if not decisions or not isinstance(decisions, dict):
                print("[WARNING] Invalid AI response format, using default hold strategy")
                print(f"[DEBUG] Response content: {response[:200]}...")
                return self._get_default_decisions(market_state)
            
            elapsed_time = time.time() - start_time
            print(f"[SUCCESS] AI决策生成成功 (耗时: {elapsed_time:.2f}秒, 决策: {len(decisions)}个)")
            
            # 记录决策质量
            ai_decisions = 0
            hold_decisions = 0
            action_decisions = 0
            
            for coin, decision in decisions.items():
                if isinstance(decision, dict):
                    signal = decision.get('signal', 'hold')
                    if signal == 'hold':
                        hold_decisions += 1
                    else:
                        action_decisions += 1
                    ai_decisions += 1
            
            print(f"[INFO] 决策分布: {action_decisions}个操作, {hold_decisions}个持有")
            
            return decisions
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_str = str(e).lower()
            
            # 分类错误类型
            if "timeout" in error_str:
                print(f"[ERROR] AI决策超时 (耗时: {elapsed_time:.2f}秒): {e}")
            elif "connection" in error_str:
                print(f"[ERROR] AI连接失败 (耗时: {elapsed_time:.2f}秒): {e}")
            elif "401" in error_str or "403" in error_str:
                print(f"[ERROR] AI认证失败: {e}")
            elif "429" in error_str:
                print(f"[ERROR] AI限流: {e}")
            else:
                print(f"[ERROR] AI决策失败 (耗时: {elapsed_time:.2f}秒): {e}")
            
            print(f"[INFO] 使用默认持有策略")
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
        # Use custom system prompt if provided, otherwise use enhanced default
        if self.system_prompt.strip():
            system_role = self.system_prompt.strip()
        else:
            system_role = self._get_enhanced_default_prompt()
        
        # If using enhanced prompt, build comprehensive data
        if not self.system_prompt.strip():
            return self._build_enhanced_prompt(market_state, portfolio, account_info)
        
        # Fallback to original prompt format
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
    
    def _get_enhanced_default_prompt(self) -> str:
        """Get enhanced default trading prompt"""
        return """你是一位顶尖的加密货币交易分析师。请结合以下最新的市场数据、技术指标、当前持仓信息、账户总览信息以及止盈止损订单信息，为加密货币合约提供一个详细的交易策略。"""
    
    def _build_enhanced_prompt(self, market_state: Dict, portfolio: Dict, account_info: Dict) -> str:
        """Build enhanced comprehensive trading prompt"""
        
        # Build K-line data string
        all_klines_string = self._build_klines_data(market_state)
        
        # Build technical indicators data
        indicators_data_string = self._build_indicators_data(market_state)
        
        # Build position info
        position_info_string = self._build_position_info(portfolio)
        
        # Build stop loss/take profit orders (simulated for now)
        tpsl_orders_string = self._build_tpsl_orders(portfolio)
        
        # Build trigger orders (simulated for now)
        trigger_orders_string = "[]"  # No trigger orders in current system
        
        prompt = f"""你是一位顶尖的加密货币交易分析师。请结合以下最新的市场数据、技术指标、当前持仓信息、账户总览信息以及止盈止损订单信息，为加密货币合约提供一个详细的交易策略。

**1. K线数据 (多时间周期):**
每行格式: 币种, 当前价格, 24h涨跌幅, 7日涨跌幅, 成交量趋势
{all_klines_string}

**2. 技术指标数据:**
```json
{indicators_data_string}
```

**3. 当前持仓信息:**
```json
{position_info_string}
```

**4. 账户总览信息:**
- 初始资金: ${account_info['initial_capital']:,.2f}
- 当前总值: ${portfolio['total_value']:,.2f}
- 可用现金: ${portfolio['cash']:,.2f}
- 总收益率: {account_info['total_return']:+.2f}%

**5. 止盈止损订单当前委托:**
```json
{tpsl_orders_string}
```

**6. 计划委托当前委托:**
```json
{trigger_orders_string}
```

**分析要求:**
请严格按照以下结构进行分析和输出：

1. **市场趋势判断**:
   - **综合判断**: 结合 K 线形态、成交量和所有技术指标（SMA, RSI等），明确判断当前市场的主要趋势是 **上涨**、**下跌** 还是 **震荡**。
   - **判断信心度**: 以百分比形式给出你对趋势判断的信心度 (例如: 信心度: 85%)。
   - **关键指标解读**: 简要说明几个关键指标是如何支持你的趋势判断的。

2. **关键价位识别**:
   - **支撑位**: 识别出 1-2 个最关键的短期支撑位。
   - **压力位**: 识别出 1-2 个最关键的短期压力位。

3. **交易策略与操作建议**:
   - **基本原则**: 只有在市场出现明确的 **上涨** 或 **下跌** 趋势时才进行操作。如果判断为 **震荡** 或趋势不明朗，则首选 **保持观望 (Wait)**。
   - **操作方向**: 明确建议 **做多 (Long)**、**做空 (Short)** 或 **保持观望 (Wait)**。
   - **入场点位 (Entry Point)**: 如果建议操作，推荐一个具体的、可操作的明确入场价格点位。如果建议观望，则此处写"无"。
   - **止盈位 (Take Profit)**: 如果建议操作，推荐一个明确的止盈价格。如果建议观望，则此处写"无"。
   - **止损位 (Stop Loss)**: 如果建议操作，推荐一个明确的止损价格。如果建议观望，则此处写"无"。
   - **持仓调整建议**: 根据当前持仓，给出相应的调整建议（例如：减仓、加仓、平仓等）。

4. **最终操作建议**:
   根据以上所有信息，从以下操作中选择 **一个或多个** 最应该执行的操作：
   1. **立即平仓**: (如果判断现有仓位风险过高或市场趋势明确反转)
   2. **开多仓**: (如果判断上涨趋势明确)
   3. **开空仓**: (如果判断下跌趋势明确)
   4. **调整止盈止损**: (如果现有仓位需要调整风险控制)
   5. **保持观望**: (如果市场趋势不明朗)

**输出格式要求 (JSON):**
```json
{{
  "market_analysis": {{
    "trend": "上涨|下跌|震荡",
    "confidence": 85,
    "key_indicators": "关键指标解读"
  }},
  "key_levels": {{
    "support": [价格1, 价格2],
    "resistance": [价格1, 价格2]
  }},
  "trading_decisions": {{
    "BTC": {{
      "signal": "buy_to_enter|sell_to_enter|close_position|hold",
      "quantity": 0.1,
      "leverage": 5,
      "entry_price": 45000,
      "profit_target": 47000,
      "stop_loss": 43000,
      "confidence": 0.8,
      "justification": "详细的技术和基本面分析理由",
      "risk_assessment": "low|medium|high"
    }}
  }},
  "final_recommendations": [
    "操作建议1",
    "操作建议2"
  ]
}}
```

请确保你的分析逻辑清晰、依据充分，并直接给出JSON格式的操作建议。"""
        
        return prompt
    
    def _build_klines_data(self, market_state: Dict) -> str:
        """Build K-line data string"""
        klines_data = []
        for coin, data in market_state.items():
            price = data.get('price', 0)
            change_24h = data.get('change_24h', 0)
            indicators = data.get('indicators', {})
            change_7d = indicators.get('price_change_7d', 0)
            
            # Simulate volume trend
            volume_trend = "增加" if change_24h > 0 else "减少"
            
            klines_data.append(f"{coin}, ${price:.2f}, {change_24h:+.2f}%, {change_7d:+.2f}%, 成交量{volume_trend}")
        
        return "\n".join(klines_data)
    
    def _build_indicators_data(self, market_state: Dict) -> str:
        """Build technical indicators data"""
        indicators_data = {}
        
        for coin, data in market_state.items():
            indicators = data.get('indicators', {})
            if indicators:
                indicators_data[coin] = {
                    "SMA_7": round(indicators.get('sma_7', 0), 2),
                    "SMA_14": round(indicators.get('sma_14', 0), 2),
                    "RSI_14": round(indicators.get('rsi_14', 50), 1),
                    "current_price": round(data.get('price', 0), 2),
                    "price_change_7d": round(indicators.get('price_change_7d', 0), 2)
                }
        
        import json
        return json.dumps(indicators_data, indent=2, ensure_ascii=False)
    
    def _build_position_info(self, portfolio: Dict) -> str:
        """Build position information"""
        positions_data = []
        
        for position in portfolio.get('positions', []):
            pos_data = {
                "coin": position.get('coin', ''),
                "side": position.get('side', ''),
                "quantity": position.get('quantity', 0),
                "avg_price": position.get('avg_price', 0),
                "current_price": position.get('current_price', position.get('avg_price', 0)),
                "leverage": position.get('leverage', 1),
                "unrealized_pnl": position.get('pnl', 0),
                "margin": position.get('margin', 0)
            }
            positions_data.append(pos_data)
        
        import json
        return json.dumps(positions_data, indent=2, ensure_ascii=False)
    
    def _build_tpsl_orders(self, portfolio: Dict) -> str:
        """Build stop loss/take profit orders info"""
        # For now, simulate based on positions
        tpsl_orders = []
        
        for position in portfolio.get('positions', []):
            coin = position.get('coin', '')
            side = position.get('side', '')
            current_price = position.get('current_price', position.get('avg_price', 0))
            
            if side == 'long':
                stop_loss = current_price * 0.95  # -5%
                take_profit = current_price * 1.15  # +15%
            else:
                stop_loss = current_price * 1.05  # +5% for short
                take_profit = current_price * 0.85  # -15% for short
            
            tpsl_orders.append({
                "coin": coin,
                "position_side": side,
                "stop_loss_price": round(stop_loss, 2),
                "take_profit_price": round(take_profit, 2),
                "status": "active"
            })
        
        import json
        return json.dumps(tpsl_orders, indent=2, ensure_ascii=False)
    
    def _call_llm(self, prompt: str) -> str:
        """调用LLM API，带重试机制和改进的错误处理"""
        import requests
        import json
        import os
        import time
        
        # 重试配置
        max_retries = 3
        base_timeout = 45  # 增加基础超时时间
        retry_delays = [1, 3, 5]  # 重试间隔
        
        for attempt in range(max_retries):
            try:
                print(f"[INFO] AI API调用尝试 {attempt + 1}/{max_retries}")
                
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
                    
                    # 动态调整超时时间
                    timeout = base_timeout + (attempt * 15)  # 每次重试增加15秒
                    
                    start_time = time.time()
                    response = session.post(
                        api_url,
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )
                    elapsed_time = time.time() - start_time
                    
                    print(f"[INFO] API响应时间: {elapsed_time:.2f}秒")
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result['choices'][0]['message']['content']
                        print(f"[SUCCESS] AI API调用成功 (尝试 {attempt + 1})")
                        return content
                    else:
                        error_msg = f"API request failed with status {response.status_code}: {response.text[:200]}"
                        print(f"[ERROR] {error_msg}")
                        
                        # 对于某些错误码，不进行重试
                        if response.status_code in [401, 403, 429]:
                            if response.status_code == 429:
                                print(f"[WARNING] API限流，等待更长时间后重试")
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delays[attempt] * 3)  # 限流时等待更长时间
                                    continue
                            raise Exception(error_msg)
                        
                        if attempt == max_retries - 1:
                            raise Exception(error_msg)
                        
                finally:
                    # 恢复代理环境变量
                    for var, value in saved_proxies.items():
                        os.environ[var] = value
                
            except requests.exceptions.Timeout:
                error_msg = f"API request timeout (attempt {attempt + 1}, timeout: {timeout}s)"
                print(f"[WARNING] {error_msg}")
                if attempt == max_retries - 1:
                    raise Exception("API request timeout after retries")
                
            except requests.exceptions.ConnectionError as e:
                error_msg = f"API connection failed (attempt {attempt + 1}): {str(e)}"
                print(f"[WARNING] {error_msg}")
                if attempt == max_retries - 1:
                    raise Exception(f"API connection failed after retries: {str(e)}")
                
            except requests.exceptions.RequestException as e:
                error_msg = f"API request error (attempt {attempt + 1}): {str(e)}"
                print(f"[WARNING] {error_msg}")
                if attempt == max_retries - 1:
                    raise Exception(f"API request error after retries: {str(e)}")
                
            except json.JSONDecodeError as e:
                error_msg = f"API response parsing failed (attempt {attempt + 1}): {str(e)}"
                print(f"[WARNING] {error_msg}")
                if attempt == max_retries - 1:
                    raise Exception(f"API response parsing failed after retries: {str(e)}")
                
            except KeyError as e:
                error_msg = f"API response format error (attempt {attempt + 1}): missing {str(e)}"
                print(f"[WARNING] {error_msg}")
                if attempt == max_retries - 1:
                    raise Exception(f"API response format error after retries: missing {str(e)}")
                
            except Exception as e:
                error_msg = f"Unexpected error (attempt {attempt + 1}): {str(e)}"
                print(f"[WARNING] {error_msg}")
                if attempt == max_retries - 1:
                    raise Exception(f"Unexpected error after retries: {str(e)}")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                print(f"[INFO] 等待 {delay}秒后重试...")
                time.sleep(delay)
        
        # 如果所有重试都失败了
        raise Exception("All retry attempts failed")
    
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
