# AITradeGame 大模型的交易能力测试项目

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![OKX Integration](https://img.shields.io/badge/OKX-integrated-orange.svg)](https://www.okx.com/)

基于 Web 的加密货币交易平台，采用 AI 驱动的决策系统，支持模拟交易和 OKX 实盘交易。

## 功能特性

### 🤖 AI 交易核心

- 实时加密货币市场数据集成 (Binance + CoinGecko)
- 基于大语言模型的增强 AI 交易策略
- 动态交易频率和币种配置
- 自定义系统提示词支持

### 💼 投资组合管理

- 支持杠杆的智能投资组合管理
- 实时图表的交互式仪表板
- 交易历史与性能跟踪
- 多模型并行交易支持

### 🛡️ 风险管理系统

- **智能风险控制**: 自动订单验证和风险限制
- **止损止盈**: 自动执行止损(-5%)和止盈(+15%)
- **仓位管理**: 最多 3 个持仓，每笔交易最大 5%风险
- **杠杆限制**: 最大 20 倍杠杆保护

### 📊 监控报警系统

- **实时监控**: 结构化日志和事件追踪
- **智能报警**: 大额亏损、高杠杆、API 错误自动报警
- **健康检查**: 系统状态和性能指标监控
- **性能分析**: 胜率、盈亏比、最大回撤等指标

### 🔗 交易接口

- OKX 实盘交易集成 (支持沙盒和实盘)
- API 凭证安全加密存储
- 智能错误处理和重试机制
- 双向持仓模式支持

## 技术栈

- 后端：Python/Flask
- 前端：原生 JavaScript、ECharts
- 数据库：SQLite
- AI 接口：OpenAI 兼容格式（支持 OpenAI、DeepSeek、Claude 等）
- 交易接口：OKX REST API（支持模拟和实盘交易）
- 安全加密：cryptography 库（Fernet 对称加密）

## 安装

```bash
pip install -r requirements.txt

# 推荐使用安全启动脚本
python start.py

# 或直接启动
python app.py
```

访问地址：`http://localhost:5000`

## 配置

### AI 模型配置

通过 Web 界面添加交易模型：

- 模型名称
- API 密钥
- API 地址
- 模型标识符
- 初始资金

### OKX 交易配置（可选）

如需使用 OKX 实盘交易，需要配置：

- OKX API Key
- OKX Secret Key
- OKX Passphrase
- 沙盒模式开关（推荐先使用沙盒测试）

**获取 OKX API 凭证：**

1. 登录 [OKX](https://www.okx.com/) 账户
2. 进入 API 管理页面
3. 创建新的 API Key
4. 设置适当的权限（交易权限）
5. 记录 API Key、Secret Key 和 Passphrase

**安全提示：**

- API 凭证会自动加密存储
- 建议先在沙盒环境测试
- 请妥善保管您的 API 凭证

## 项目结构

```
trading_bot/
├── app.py                    # Flask 应用主程序
├── trading_engine.py         # 交易逻辑引擎
├── ai_trader.py              # AI 集成模块
├── database.py               # 数据层
├── market_data.py            # 市场数据接口
├── okx_client.py             # OKX API 客户端
├── secure_storage.py         # 安全存储模块
├── test_okx_integration.py   # 集成测试
├── static/                   # CSS/JS 资源
├── templates/                # HTML 模板
└── requirements.txt          # Python 依赖
```

## 支持的 AI 模型

兼容 OpenAI 格式的 API：

- OpenAI (gpt-4, gpt-3.5-turbo)
- DeepSeek (deepseek-chat)
- Claude (通过 OpenRouter)

## 使用方法

1. 启动服务器
2. 添加 AI 模型配置
3. 系统自动开始交易
4. 实时监控投资组合

## 使用指南

### 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 启动服务：`python app.py`
3. 访问：`http://localhost:5000`
4. 添加 AI 模型配置
5. （可选）配置 OKX API 进行实盘交易

### 交易模式

- **模拟模式**：仅配置 AI 模型，使用虚拟资金进行纸面交易
- **OKX 模式**：额外配置 OKX API，使用真实的 OKX 账户进行交易

## 故障排除

### 常见问题

**Q: OKX API 认证失败**
A: 请检查：

- API Key、Secret Key、Passphrase 是否正确
- API Key 是否有交易权限
- 是否选择了正确的环境（沙盒/实盘）

**Q: 加密库安装失败**
A: 安装 cryptography 库：

```bash
pip install cryptography
```

如果仍然失败，系统会自动降级到 base64 编码。

**Q: AI API 超时或连接失败**
A: 系统会自动：

- 使用默认的"持仓"策略
- 记录错误日志
- 在下个周期重试

检查网络连接和 AI API 服务状态

**Q: 交易执行失败**
A: 检查：

- 账户余额是否充足
- 交易对是否支持
- 网络连接是否正常
- OKX API 服务状态

**Q: 前端无法加载**
A: 确保：

- Flask 服务正常启动
- 端口 5000 未被占用
- 浏览器支持现代 JavaScript

## 注意事项

- **风险提示**：实盘交易涉及真实资金，请谨慎操作
- 建议先在沙盒环境充分测试
- 需要有效的 AI 模型 API 密钥
- 需要互联网连接以获取市场数据
- OKX API 有频率限制，系统已自动处理

## 贡献

欢迎贡献代码！

**免责声明**：本平台仅用于教育和模拟目的，不构成任何投资建议。请谨慎操作。开发者不承担任何交易损失责任。
