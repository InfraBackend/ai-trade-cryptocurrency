# OKX 交易集成设置指南

本指南将帮助您快速设置 OKX 实盘交易功能。

## 前置要求

1. Python 3.9+ 环境
2. OKX 账户（如需实盘交易）
3. AI 模型 API 访问权限（OpenAI、DeepSeek 等）

## 步骤 1：安装依赖

```bash
# 克隆项目
git clone <repository-url>
cd AITradeGame

# 安装 Python 依赖
pip install -r requirements.txt
```

## 步骤 2：获取 OKX API 凭证

### 2.1 登录 OKX

访问 [OKX 官网](https://www.okx.com/) 并登录您的账户。

### 2.2 创建 API Key

1. 进入 **账户设置** > **API 管理**
2. 点击 **创建 API Key**
3. 设置 API Key 名称
4. 选择权限：
   - ✅ **交易** (必需)
   - ✅ **读取** (必需)
   - ❌ **提现** (不推荐)
5. 设置 IP 白名单（可选，但推荐）
6. 记录以下信息：
   - **API Key**
   - **Secret Key**
   - **Passphrase**

⚠️ **重要**：Secret Key 只显示一次，请妥善保存！

## 步骤 3：启动应用

```bash
python app.py
```

访问：http://localhost:5000

## 步骤 4：配置交易模型

### 4.1 添加 AI 模型

1. 点击 **"添加模型"** 按钮
2. 填写 AI 模型信息：
   - **名称**：自定义名称
   - **API 密钥**：您的 AI API Key
   - **API 地址**：如 `https://api.openai.com`
   - **模型名称**：如 `gpt-4`
   - **初始资金**：如 `10000`

### 4.2 配置 OKX（可选）

在同一表单中填写 OKX 配置：

- **OKX API Key**：步骤 2 获取的 API Key
- **OKX Secret Key**：步骤 2 获取的 Secret Key
- **OKX Passphrase**：步骤 2 获取的 Passphrase
- **沙盒模式**：✅ 推荐先启用进行测试

### 4.3 测试配置

点击 **"测试 OKX 配置"** 按钮验证设置是否正确。

## 步骤 5：开始交易

1. 选择已配置的模型
2. 查看实时数据和 AI 决策
3. 监控交易执行和账户状态

## 安全建议

### 🔒 API 安全

- 使用强密码保护 OKX 账户
- 启用双因素认证 (2FA)
- 设置 IP 白名单限制 API 访问
- 定期轮换 API 密钥

### 💰 资金安全

- **强烈建议先在沙盒环境测试**
- 设置合理的初始资金
- 监控交易频率和金额
- 设置止损策略

### 🔐 系统安全

- API 凭证自动加密存储
- 设置环境变量增强安全性：
  ```bash
  export TRADING_BOT_SECRET_KEY="your-custom-encryption-key"
  ```

## 故障排除

### 问题：OKX API 认证失败

**解决方案：**

1. 检查 API Key、Secret Key、Passphrase 是否正确
2. 确认 API Key 有交易权限
3. 检查 IP 是否在白名单中
4. 确认选择了正确的环境（沙盒/实盘）

### 问题：交易执行失败

**解决方案：**

1. 检查账户余额是否充足
2. 确认交易对支持（BTC-USDT、ETH-USDT 等）
3. 检查网络连接
4. 查看 OKX API 服务状态

### 问题：加密库安装失败

**解决方案：**

```bash
# 尝试升级 pip
pip install --upgrade pip

# 安装加密库
pip install cryptography

# 如果仍然失败，系统会自动降级到 base64 编码
```

## 高级配置

### 环境变量

```bash
# 设置加密密钥
export TRADING_BOT_SECRET_KEY="your-secret-key"

# 设置数据库路径
export DATABASE_PATH="/path/to/your/database.db"
```

### 自定义配置

复制 `config.example.py` 为 `config.py` 并修改相关设置。

## 测试验证

运行集成测试确保一切正常：

```bash
python test_okx_integration.py
```

## 支持

如遇问题，请：

1. 查看控制台日志
2. 检查 OKX API 文档
3. 运行集成测试诊断问题
4. 提交 Issue 并附上错误日志

---

**免责声明**：本软件仅供学习和研究使用。实盘交易涉及真实资金风险，请谨慎操作。开发者不承担任何交易损失责任。
