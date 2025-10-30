class TradingApp {
  constructor() {
    this.currentModelId = null;
    this.editingModelId = null;
    this.chart = null;
    this.refreshIntervals = {
      market: null,
      portfolio: null,
      trades: null,
    };
    this.init();
  }

  init() {
    this.initEventListeners();
    this.loadModels();
    this.loadMarketPrices();
    this.startRefreshCycles();
  }

  initEventListeners() {
    document
      .getElementById("addModelBtn")
      .addEventListener("click", () => this.showModal());
    document
      .getElementById("closeModalBtn")
      .addEventListener("click", () => this.hideModal());
    document
      .getElementById("cancelBtn")
      .addEventListener("click", () => this.hideModal());
    document
      .getElementById("submitBtn")
      .addEventListener("click", () => this.submitModel());
    document
      .getElementById("refreshBtn")
      .addEventListener("click", () => this.refresh());
    document
      .getElementById("testOkxBtn")
      .addEventListener("click", () => this.testOkxConfig());
    document
      .getElementById("manualTradeBtn")
      .addEventListener("click", () => this.executeManualTrade());

    // AI Trading Result Modal event listeners
    document
      .getElementById("closeAiResultBtn")
      .addEventListener("click", () => this.hideAiTradingModal());
    document
      .getElementById("confirmAiResultBtn")
      .addEventListener("click", () => this.hideAiTradingModal());

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", (e) =>
        this.switchTab(e.target.dataset.tab)
      );
    });
  }

  async loadModels() {
    try {
      const response = await fetch("/api/models");
      const models = await response.json();
      this.renderModels(models);

      if (models.length > 0 && !this.currentModelId) {
        this.selectModel(models[0].id);
      }
    } catch (error) {
      console.error("Failed to load models:", error);
    }
  }

  renderModels(models) {
    const container = document.getElementById("modelList");

    if (models.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无模型</div>';
      return;
    }

    container.innerHTML = models
      .map(
        (model) => `
            <div class="model-item ${
              model.id === this.currentModelId ? "active" : ""
            }" 
                 onclick="app.selectModel(${model.id})">
                <div class="model-name">
                    ${model.name}
                    <span class="trading-mode ${
                      model.trading_mode === "OKX" ? "okx-mode" : "sim-mode"
                    }">
                        ${model.trading_mode}
                    </span>
                </div>
                <div class="model-info">
                    <span>${model.model_name}</span>
                    <div class="model-config">
                        <small class="config-item">
                            <i class="bi bi-clock"></i>
                            ${Math.round(
                              (model.trading_frequency || 180) / 60
                            )}分钟
                        </small>
                        <small class="config-item ${
                          model.auto_trading_enabled ? "enabled" : "disabled"
                        }">
                            <i class="bi bi-${
                              model.auto_trading_enabled
                                ? "play-circle"
                                : "pause-circle"
                            }"></i>
                            ${model.auto_trading_enabled ? "自动" : "手动"}
                        </small>
                        <small class="config-item">
                            <i class="bi bi-currency-bitcoin"></i>
                            ${
                              (
                                model.trading_coins ||
                                "BTC,ETH,SOL,BNB,XRP,DOGE"
                              ).split(",").length
                            }币种
                        </small>
                    </div>
                    <div class="model-actions">
                        <span class="model-edit" onclick="event.stopPropagation(); app.editModel(${
                          model.id
                        })" title="编辑模型">
                            <i class="bi bi-pencil"></i>
                        </span>
                        <span class="model-delete" onclick="event.stopPropagation(); app.deleteModel(${
                          model.id
                        })" title="删除模型">
                            <i class="bi bi-trash"></i>
                        </span>
                    </div>
                </div>
            </div>
        `
      )
      .join("");
  }

  async selectModel(modelId) {
    this.currentModelId = modelId;
    this.loadModels();
    await this.loadModelData();

    // 更新手动交易按钮状态
    this.updateManualTradeButton();
  }

  updateManualTradeButton() {
    const manualTradeBtn = document.getElementById("manualTradeBtn");
    if (this.currentModelId) {
      manualTradeBtn.disabled = false;
      manualTradeBtn.title = "执行AI交易决策";
    } else {
      manualTradeBtn.disabled = true;
      manualTradeBtn.title = "请先选择一个模型";
    }
  }

  async loadModelData() {
    if (!this.currentModelId) return;

    try {
      const [portfolio, trades, conversations] = await Promise.all([
        fetch(`/api/models/${this.currentModelId}/portfolio`).then((r) =>
          r.json()
        ),
        fetch(`/api/models/${this.currentModelId}/trades?limit=50`).then((r) =>
          r.json()
        ),
        fetch(`/api/models/${this.currentModelId}/conversations?limit=20`).then(
          (r) => r.json()
        ),
      ]);

      this.updateStats(portfolio.portfolio);
      this.updateChart(
        portfolio.account_value_history,
        portfolio.portfolio.total_value
      );
      this.updatePositions(portfolio.portfolio.positions);
      this.updateTrades(trades);
      this.updateConversations(conversations);
    } catch (error) {
      console.error("Failed to load model data:", error);
    }
  }

  updateStats(portfolio) {
    if (!portfolio) {
      console.warn("Portfolio data is null or undefined");
      return;
    }

    const totalValue = portfolio.total_value || 0;
    const initialCapital = portfolio.initial_capital || 1;
    const cash = portfolio.cash || 0;
    const positionsValue = portfolio.positions_value || 0;
    const realizedPnl = portfolio.realized_pnl || 0;
    const unrealizedPnl = portfolio.unrealized_pnl || 0;

    // 计算各种百分比
    const totalReturn = ((totalValue - initialCapital) / initialCapital) * 100;
    // 现金占比和保证金占比应该相加等于100%（或接近100%）
    const cashPercentage = totalValue > 0 ? (cash / totalValue) * 100 : 0;
    const marginPercentage = totalValue > 0 ? (positionsValue / totalValue) * 100 : 0;
    const realizedPnlPercent = (realizedPnl / initialCapital) * 100;
    const unrealizedPnlPercent = (unrealizedPnl / initialCapital) * 100;

    // 1. 账户总值
    const accountValueEl = document.getElementById("accountValue");
    const accountChangeEl = document.getElementById("accountChange");
    const totalReturnPercentEl = document.getElementById("totalReturnPercent");

    if (accountValueEl) {
      accountValueEl.textContent = `$${totalValue.toFixed(2)}`;
      accountValueEl.className = `stat-value ${totalReturn > 0 ? "positive" : totalReturn < 0 ? "negative" : ""}`;
    }

    if (accountChangeEl) {
      accountChangeEl.textContent = `${totalReturn > 0 ? "+" : ""}${totalReturn.toFixed(2)}%`;
      accountChangeEl.className = `stat-change ${totalReturn > 0 ? "positive" : totalReturn < 0 ? "negative" : ""}`;
    }

    if (totalReturnPercentEl) {
      totalReturnPercentEl.textContent = `${totalReturn > 0 ? "+" : ""}${totalReturn.toFixed(2)}%`;
      totalReturnPercentEl.className = `detail-value ${totalReturn > 0 ? "positive" : totalReturn < 0 ? "negative" : ""}`;
    }

    // 2. 可用现金
    const cashValueEl = document.getElementById("cashValue");
    const cashPercentageEl = document.getElementById("cashPercentage");
    const positionPercentEl = document.getElementById("positionPercent");

    if (cashValueEl) {
      cashValueEl.textContent = `$${cash.toFixed(2)}`;
    }

    if (cashPercentageEl) {
      cashPercentageEl.textContent = `现金占比: ${cashPercentage.toFixed(1)}%`;
    }

    if (positionPercentEl) {
      positionPercentEl.textContent = `${marginPercentage.toFixed(1)}%`;
    }

    // 3. 已实现盈亏
    const realizedPnlEl = document.getElementById("realizedPnl");
    const realizedPnlPercentEl = document.getElementById("realizedPnlPercent");

    if (realizedPnlEl) {
      realizedPnlEl.textContent = `${realizedPnl >= 0 ? "+" : ""}$${Math.abs(realizedPnl).toFixed(2)}`;
      realizedPnlEl.className = `stat-value pnl-value ${realizedPnl > 0 ? "positive" : realizedPnl < 0 ? "negative" : ""}`;
    }

    if (realizedPnlPercentEl) {
      realizedPnlPercentEl.textContent = `${realizedPnlPercent >= 0 ? "+" : ""}${realizedPnlPercent.toFixed(2)}%`;
      realizedPnlPercentEl.className = `stat-percentage pnl-percentage ${realizedPnl > 0 ? "positive" : realizedPnl < 0 ? "negative" : ""}`;
    }

    // 4. 未实现盈亏
    const unrealizedPnlEl = document.getElementById("unrealizedPnl");
    const unrealizedPnlPercentEl = document.getElementById("unrealizedPnlPercent");

    if (unrealizedPnlEl) {
      unrealizedPnlEl.textContent = `${unrealizedPnl >= 0 ? "+" : ""}$${Math.abs(unrealizedPnl).toFixed(2)}`;
      unrealizedPnlEl.className = `stat-value pnl-value ${unrealizedPnl > 0 ? "positive" : unrealizedPnl < 0 ? "negative" : ""}`;
    }

    if (unrealizedPnlPercentEl) {
      unrealizedPnlPercentEl.textContent = `${unrealizedPnlPercent >= 0 ? "+" : ""}${unrealizedPnlPercent.toFixed(2)}%`;
      unrealizedPnlPercentEl.className = `stat-percentage pnl-percentage ${unrealizedPnl > 0 ? "positive" : unrealizedPnl < 0 ? "negative" : ""}`;
    }
  }

  updateChart(history, currentValue) {
    const chartDom = document.getElementById("accountChart");

    if (!this.chart) {
      this.chart = echarts.init(chartDom);
      window.addEventListener("resize", () => {
        if (this.chart) {
          this.chart.resize();
        }
      });
    }

    const data = history.reverse().map((h) => ({
      time: new Date(h.timestamp.replace(" ", "T") + "Z").toLocaleTimeString(
        "zh-CN",
        {
          timeZone: "Asia/Shanghai",
          hour: "2-digit",
          minute: "2-digit",
        }
      ),
      value: h.total_value,
    }));

    if (currentValue !== undefined && currentValue !== null) {
      const now = new Date();
      const currentTime = now.toLocaleTimeString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour: "2-digit",
        minute: "2-digit",
      });
      data.push({
        time: currentTime,
        value: currentValue,
      });
    }

    const option = {
      grid: {
        left: "60",
        right: "20",
        bottom: "30",
        top: "20",
        containLabel: false,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: data.map((d) => d.time),
        axisLine: { lineStyle: { color: "#e5e6eb" } },
        axisLabel: { color: "#86909c", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { lineStyle: { color: "#e5e6eb" } },
        axisLabel: {
          color: "#86909c",
          fontSize: 11,
          formatter: (value) => `$${value.toLocaleString()}`,
        },
        splitLine: { lineStyle: { color: "#f2f3f5" } },
      },
      series: [
        {
          type: "line",
          data: data.map((d) => d.value),
          smooth: true,
          symbol: "none",
          lineStyle: { color: "#3370ff", width: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(51, 112, 255, 0.2)" },
                { offset: 1, color: "rgba(51, 112, 255, 0)" },
              ],
            },
          },
        },
      ],
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255, 255, 255, 0.95)",
        borderColor: "#e5e6eb",
        borderWidth: 1,
        textStyle: { color: "#1d2129" },
        formatter: (params) => {
          const value = params[0].value;
          return `${params[0].axisValue}<br/>$${value.toFixed(2)}`;
        },
      },
    };

    this.chart.setOption(option);

    setTimeout(() => {
      if (this.chart) {
        this.chart.resize();
      }
    }, 100);
  }

  updatePositions(positions) {
    const tbody = document.getElementById("positionsBody");

    if (positions.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="empty-state">暂无持仓</td></tr>';
      return;
    }

    tbody.innerHTML = positions
      .map((pos) => {
        const sideClass = pos.side === "long" ? "badge-long" : "badge-short";
        const sideText = pos.side === "long" ? "做多" : "做空";

        const currentPrice =
          pos.current_price !== null && pos.current_price !== undefined
            ? `$${pos.current_price.toFixed(2)}`
            : "-";

        let pnlDisplay = "-";
        let pnlClass = "";
        if (pos.pnl !== undefined && pos.pnl !== 0) {
          pnlClass = pos.pnl > 0 ? "text-success" : "text-danger";
          pnlDisplay = `${pos.pnl > 0 ? "+" : ""}$${pos.pnl.toFixed(2)}`;
        }

        return `
                <tr>
                    <td><strong>${pos.coin}</strong></td>
                    <td><span class="badge ${sideClass}">${sideText}</span></td>
                    <td>${pos.quantity.toFixed(4)}</td>
                    <td>$${pos.avg_price.toFixed(2)}</td>
                    <td>${currentPrice}</td>
                    <td>${pos.leverage}x</td>
                    <td class="${pnlClass}"><strong>${pnlDisplay}</strong></td>
                </tr>
            `;
      })
      .join("");
  }

  updateTrades(trades) {
    const tbody = document.getElementById("tradesBody");

    if (trades.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="6" class="empty-state">暂无交易记录</td></tr>';
      return;
    }

    tbody.innerHTML = trades
      .map((trade) => {
        const signalMap = {
          buy_to_enter: { badge: "badge-buy", text: "开多" },
          sell_to_enter: { badge: "badge-sell", text: "开空" },
          close_position: { badge: "badge-close", text: "平仓" },
        };
        const signal = signalMap[trade.signal] || {
          badge: "",
          text: trade.signal,
        };
        const pnlClass =
          trade.pnl > 0 ? "text-success" : trade.pnl < 0 ? "text-danger" : "";

        return `
                <tr>
                    <td>${new Date(
                      trade.timestamp.replace(" ", "T") + "Z"
                    ).toLocaleString("zh-CN", {
                      timeZone: "Asia/Shanghai",
                    })}</td>
                    <td><strong>${trade.coin}</strong></td>
                    <td><span class="badge ${signal.badge}">${
          signal.text
        }</span></td>
                    <td>${trade.quantity.toFixed(4)}</td>
                    <td>$${trade.price.toFixed(2)}</td>
                    <td class="${pnlClass}">$${trade.pnl.toFixed(2)}</td>
                </tr>
            `;
      })
      .join("");
  }

  updateConversations(conversations) {
    const container = document.getElementById("conversationsBody");

    if (conversations.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无对话记录</div>';
      return;
    }

    container.innerHTML = conversations
      .map(
        (conv) => `
            <div class="conversation-item">
                <div class="conversation-time">${new Date(
                  conv.timestamp.replace(" ", "T") + "Z"
                ).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}</div>
                <div class="conversation-content">${conv.ai_response}</div>
            </div>
        `
      )
      .join("");
  }

  async loadMarketPrices() {
    try {
      const response = await fetch("/api/market/prices");
      const prices = await response.json();
      this.renderMarketPrices(prices);

      // Also load data source status
      this.loadDataSourceStatus();
    } catch (error) {
      console.error("Failed to load market prices:", error);
      this.showDataSourceError();
    }
  }

  async loadDataSourceStatus() {
    try {
      const response = await fetch("/api/market/sources/status");
      const data = await response.json();
      this.renderDataSourceStatus(data.sources);
    } catch (error) {
      console.error("Failed to load data source status:", error);
    }
  }

  renderMarketPrices(prices) {
    const container = document.getElementById("marketPrices");

    container.innerHTML = Object.entries(prices)
      .map(([coin, data]) => {
        const changeClass = data.change_24h >= 0 ? "positive" : "negative";
        const changeIcon = data.change_24h >= 0 ? "▲" : "▼";

        return `
                <div class="price-item">
                    <div>
                        <div class="price-symbol">${coin}</div>
                        <div class="price-change ${changeClass}">${changeIcon} ${Math.abs(
          data.change_24h
        ).toFixed(2)}%</div>
                    </div>
                    <div class="price-value">$${data.price.toFixed(2)}</div>
                </div>
            `;
      })
      .join("");
  }

  renderDataSourceStatus(sources) {
    const container = document.getElementById("dataSourceStatus");
    if (!container) return;

    const sourceNames = {
      binance: "Binance",
      coingecko: "CoinGecko",
      okx: "OKX",
    };

    container.innerHTML = Object.entries(sources)
      .map(([source, status]) => {
        const statusClass =
          status === "online" ? "source-online" : "source-offline";
        const statusIcon = status === "online" ? "🟢" : "🔴";

        return `
          <div class="source-status ${statusClass}">
            <span class="source-icon">${statusIcon}</span>
            <span class="source-name">${sourceNames[source] || source}</span>
            <span class="source-status-text">${status}</span>
          </div>
        `;
      })
      .join("");
  }

  showDataSourceError() {
    const container = document.getElementById("dataSourceStatus");
    if (!container) return;

    container.innerHTML = `
      <div class="source-status source-error">
        <span class="source-icon">⚠️</span>
        <span class="source-name">数据源状态</span>
        <span class="source-status-text">获取失败</span>
      </div>
    `;
  }

  switchTab(tabName) {
    document
      .querySelectorAll(".tab-btn")
      .forEach((btn) => btn.classList.remove("active"));
    document
      .querySelectorAll(".tab-content")
      .forEach((content) => content.classList.remove("active"));

    document.querySelector(`[data-tab="${tabName}"]`).classList.add("active");
    document.getElementById(`${tabName}Tab`).classList.add("active");
  }

  showModal() {
    document.getElementById("addModelModal").classList.add("show");
  }

  hideModal() {
    document.getElementById("addModelModal").classList.remove("show");

    // 重置编辑模式
    this.editingModelId = null;

    // 重置弹窗标题和按钮文本
    document.querySelector(".modal-header h3").textContent = "添加交易模型";
    document.getElementById("submitBtn").textContent = "添加模型";
  }

  async submitModel() {
    const data = {
      name: document.getElementById("modelName").value,
      api_key: document.getElementById("apiKey").value,
      api_url: document.getElementById("apiUrl").value,
      model_name: document.getElementById("modelIdentifier").value,
      initial_capital: parseFloat(
        document.getElementById("initialCapital").value
      ),
    };

    // Add trading configuration
    const tradingFrequency =
      parseInt(document.getElementById("tradingFrequency").value) * 60; // Convert minutes to seconds
    const autoTradingEnabled =
      document.getElementById("autoTradingEnabled").checked;
    const systemPrompt = document.getElementById("systemPrompt").value.trim();

    // Get selected trading coins
    const selectedCoins = [];
    document
      .querySelectorAll('.coin-checkbox input[type="checkbox"]:checked')
      .forEach((checkbox) => {
        selectedCoins.push(checkbox.value);
      });

    if (selectedCoins.length === 0) {
      alert("请至少选择一个交易币种");
      return;
    }

    data.trading_frequency = tradingFrequency;
    data.trading_coins = selectedCoins.join(",");
    data.auto_trading_enabled = autoTradingEnabled;
    data.system_prompt = systemPrompt;

    // Add risk management configuration
    const stopLossEnabled = document.getElementById("stopLossEnabled").checked;
    const stopLossPercentage = parseFloat(
      document.getElementById("stopLossPercentage").value
    );
    const takeProfitEnabled =
      document.getElementById("takeProfitEnabled").checked;
    const takeProfitPercentage = parseFloat(
      document.getElementById("takeProfitPercentage").value
    );

    data.stop_loss_enabled = stopLossEnabled;
    data.stop_loss_percentage = stopLossPercentage;
    data.take_profit_enabled = takeProfitEnabled;
    data.take_profit_percentage = takeProfitPercentage;

    // Add OKX configuration if provided
    const okxApiKey = document.getElementById("okxApiKey").value.trim();
    const okxSecretKey = document.getElementById("okxSecretKey").value.trim();
    const okxPassphrase = document.getElementById("okxPassphrase").value.trim();
    const okxSandboxMode = document.getElementById("okxSandboxMode").checked;

    if (okxApiKey || okxSecretKey || okxPassphrase) {
      // If any OKX field is filled, validate all are filled
      if (!okxApiKey || !okxSecretKey || !okxPassphrase) {
        alert("如果要配置OKX，请填写完整的API密钥、私钥和密码短语");
        return;
      }

      data.okx_api_key = okxApiKey;
      data.okx_secret_key = okxSecretKey;
      data.okx_passphrase = okxPassphrase;
      data.okx_sandbox_mode = okxSandboxMode;
    }

    if (!data.name || !data.api_key || !data.api_url || !data.model_name) {
      alert("请填写所有必填字段");
      return;
    }

    try {
      const isEditing =
        this.editingModelId !== null && this.editingModelId !== undefined;
      const url = isEditing
        ? `/api/models/${this.editingModelId}`
        : "/api/models";
      const method = isEditing ? "PUT" : "POST";

      const response = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });

      if (response.ok) {
        this.hideModal();
        this.loadModels();
        this.clearForm();

        // 如果是编辑模式，重新加载当前模型数据
        if (isEditing && this.currentModelId === this.editingModelId) {
          await this.loadModelData();
        }
      } else {
        const errorData = await response.json();
        const action = isEditing ? "更新" : "添加";
        alert(`${action}模型失败: ${errorData.error || "未知错误"}`);
      }
    } catch (error) {
      console.error("Failed to submit model:", error);
      const action = this.editingModelId ? "更新" : "添加";
      alert(`${action}模型失败`);
    }
  }

  async editModel(modelId) {
    try {
      // 获取模型数据
      const response = await fetch(`/api/models/${modelId}`);
      if (!response.ok) {
        alert("获取模型信息失败");
        return;
      }

      const model = await response.json();

      // 填充表单数据
      document.getElementById("modelName").value = model.name || "";
      document.getElementById("apiKey").value = model.api_key || "";
      document.getElementById("apiUrl").value = model.api_url || "";
      document.getElementById("modelIdentifier").value = model.model_name || "";
      document.getElementById("initialCapital").value =
        model.initial_capital || 100000;

      // 填充交易配置
      const tradingFrequencyMinutes = Math.round(
        (model.trading_frequency || 180) / 60
      );
      document.getElementById("tradingFrequency").value =
        tradingFrequencyMinutes;
      document.getElementById("autoTradingEnabled").checked =
        model.auto_trading_enabled !== false;
      document.getElementById("systemPrompt").value = model.system_prompt || "";

      // 填充交易币种选择
      const tradingCoins = (
        model.trading_coins || "BTC,ETH,SOL,BNB,XRP,DOGE"
      ).split(",");
      document
        .querySelectorAll('.coin-checkbox input[type="checkbox"]')
        .forEach((checkbox) => {
          checkbox.checked = tradingCoins.includes(checkbox.value);
        });

      // 填充风险管理配置
      document.getElementById("stopLossEnabled").checked =
        model.stop_loss_enabled || false;
      document.getElementById("stopLossPercentage").value =
        model.stop_loss_percentage || 5.0;
      document.getElementById("takeProfitEnabled").checked =
        model.take_profit_enabled || false;
      document.getElementById("takeProfitPercentage").value =
        model.take_profit_percentage || 15.0;

      // 填充OKX配置（如果有）
      document.getElementById("okxApiKey").value = model.okx_api_key || "";
      document.getElementById("okxSecretKey").value =
        model.okx_secret_key || "";
      document.getElementById("okxPassphrase").value =
        model.okx_passphrase || "";
      document.getElementById("okxSandboxMode").checked =
        model.okx_sandbox_mode !== false;

      // 设置编辑模式
      this.editingModelId = modelId;

      // 更新弹窗标题和按钮
      document.querySelector(".modal-header h3").textContent = "编辑交易模型";
      document.getElementById("submitBtn").textContent = "更新模型";

      // 显示弹窗
      this.showModal();
    } catch (error) {
      console.error("Failed to load model for editing:", error);
      alert("加载模型信息失败");
    }
  }

  async deleteModel(modelId) {
    if (!confirm("确定要删除这个模型吗？")) return;

    try {
      const response = await fetch(`/api/models/${modelId}`, {
        method: "DELETE",
      });

      if (response.ok) {
        if (this.currentModelId === modelId) {
          this.currentModelId = null;
        }
        this.loadModels();
      }
    } catch (error) {
      console.error("Failed to delete model:", error);
    }
  }

  clearForm() {
    document.getElementById("modelName").value = "";
    document.getElementById("apiKey").value = "";
    document.getElementById("apiUrl").value = "";
    document.getElementById("modelIdentifier").value = "";
    document.getElementById("initialCapital").value = "100000";

    // Clear trading configuration
    document.getElementById("tradingFrequency").value = "3";
    document.getElementById("autoTradingEnabled").checked = true;
    document.getElementById("systemPrompt").value = "";

    // Reset coin selection to all checked
    document
      .querySelectorAll('.coin-checkbox input[type="checkbox"]')
      .forEach((checkbox) => {
        checkbox.checked = true;
      });

    // Clear risk management fields
    document.getElementById("stopLossEnabled").checked = false;
    document.getElementById("stopLossPercentage").value = "5.0";
    document.getElementById("takeProfitEnabled").checked = false;
    document.getElementById("takeProfitPercentage").value = "15.0";

    // Clear OKX fields
    document.getElementById("okxApiKey").value = "";
    document.getElementById("okxSecretKey").value = "";
    document.getElementById("okxPassphrase").value = "";
    document.getElementById("okxSandboxMode").checked = true;

    // Clear test result
    const testResult = document.getElementById("okxTestResult");
    if (testResult) {
      testResult.textContent = "";
      testResult.className = "test-result";
    }
  }

  async testOkxConfig() {
    const okxApiKey = document.getElementById("okxApiKey").value.trim();
    const okxSecretKey = document.getElementById("okxSecretKey").value.trim();
    const okxPassphrase = document.getElementById("okxPassphrase").value.trim();
    const okxSandboxMode = document.getElementById("okxSandboxMode").checked;

    const testResult = document.getElementById("okxTestResult");

    if (!okxApiKey || !okxSecretKey || !okxPassphrase) {
      testResult.textContent = "请先填写完整的OKX配置";
      testResult.className = "test-result error";
      return;
    }

    testResult.textContent = "测试中...";
    testResult.className = "test-result loading";

    try {
      const response = await fetch("/api/okx/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          okx_api_key: okxApiKey,
          okx_secret_key: okxSecretKey,
          okx_passphrase: okxPassphrase,
          okx_sandbox_mode: okxSandboxMode,
        }),
      });

      const result = await response.json();

      if (result.valid) {
        testResult.textContent = "✓ 配置有效";
        testResult.className = "test-result success";
      } else {
        testResult.textContent = `✗ ${result.message}`;
        testResult.className = "test-result error";
      }
    } catch (error) {
      console.error("Failed to test OKX config:", error);
      testResult.textContent = "✗ 测试失败";
      testResult.className = "test-result error";
    }
  }

  async executeManualTrade() {
    if (!this.currentModelId) {
      alert("请先选择一个模型");
      return;
    }

    const manualTradeBtn = document.getElementById("manualTradeBtn");
    const originalText = manualTradeBtn.innerHTML;

    try {
      // 更新按钮状态
      manualTradeBtn.disabled = true;
      manualTradeBtn.innerHTML =
        '<i class="bi bi-hourglass-split"></i> AI分析中...';

      // 显示加载中的弹窗
      this.showAiTradingModal(null, true);

      const response = await fetch(
        `/api/models/${this.currentModelId}/execute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        }
      );

      const result = await response.json();

      // 显示AI交易结果
      this.showAiTradingModal(result, false);

      if (response.ok && result.success) {
        // 刷新数据
        await this.loadModelData();
      }
    } catch (error) {
      console.error("Failed to execute manual trade:", error);
      this.showAiTradingModal(
        {
          success: false,
          error: "AI交易执行失败，请检查网络连接",
        },
        false
      );
    } finally {
      // 恢复按钮状态
      manualTradeBtn.disabled = false;
      manualTradeBtn.innerHTML = originalText;
    }
  }

  showTradeResult(result) {
    let message = "🤖 AI交易执行完成\n\n";

    if (result.decisions && Object.keys(result.decisions).length > 0) {
      message += "📊 AI决策:\n";
      for (const [coin, decision] of Object.entries(result.decisions)) {
        const signalText =
          {
            buy_to_enter: "🟢 开多",
            sell_to_enter: "🔴 开空",
            close_position: "⚪ 平仓",
            hold: "⏸️ 持有",
          }[decision.signal] || decision.signal;

        message += `${coin}: ${signalText}`;
        if (decision.quantity > 0) {
          message += ` (${decision.quantity} ${decision.leverage}x)`;
        }
        message += `\n理由: ${decision.justification}\n\n`;
      }
    }

    if (result.trades && result.trades.length > 0) {
      message += "💼 执行的交易:\n";
      for (const trade of result.trades) {
        message += `${trade.coin}: ${trade.signal} ${trade.quantity} @ $${trade.price}\n`;
      }
    } else {
      message += "📝 本次未执行任何交易";
    }

    alert(message);
  }

  async refresh() {
    await Promise.all([
      this.loadModels(),
      this.loadMarketPrices(),
      this.loadModelData(),
    ]);
  }

  startRefreshCycles() {
    // 降低市场数据刷新频率：从5秒改为30秒
    this.refreshIntervals.market = setInterval(() => {
      this.loadMarketPrices();
    }, 30000);

    // 降低投资组合数据刷新频率：从10秒改为60秒
    this.refreshIntervals.portfolio = setInterval(() => {
      if (this.currentModelId) {
        this.loadModelData();
      }
    }, 60000);
  }

  stopRefreshCycles() {
    Object.values(this.refreshIntervals).forEach((interval) => {
      if (interval) clearInterval(interval);
    });
  }

  showAiTradingModal(result, isLoading) {
    const modal = document.getElementById("aiTradingResultModal");

    if (isLoading) {
      // 显示加载状态
      document.getElementById("marketAnalysisContent").innerHTML = `
        <div class="loading-spinner">
          <div class="spinner"></div>
          AI正在分析市场数据...
        </div>
      `;
      document.getElementById("tradingDecisionsContent").innerHTML = "";
      document.getElementById("executionResultsContent").innerHTML = "";
      document.getElementById("finalRecommendationsContent").innerHTML = "";
    } else if (result) {
      // 显示结果
      this.renderAiTradingResult(result);
    }

    modal.classList.add("show");
  }

  renderAiTradingResult(result) {
    if (!result.success) {
      // 显示错误信息
      document.getElementById("marketAnalysisContent").innerHTML = `
        <div class="execution-item">
          <div class="execution-status error"></div>
          <div class="execution-text">执行失败: ${
            result.error || "未知错误"
          }</div>
        </div>
      `;
      document.getElementById("tradingDecisionsContent").innerHTML = "";
      document.getElementById("executionResultsContent").innerHTML = "";
      document.getElementById("finalRecommendationsContent").innerHTML = "";
      return;
    }

    // 解析AI响应
    let aiAnalysis = null;
    try {
      if (typeof result.decisions === "string") {
        aiAnalysis = JSON.parse(result.decisions);
      } else {
        aiAnalysis = result.decisions;
      }
    } catch (e) {
      console.warn("Failed to parse AI response as JSON, using raw response");
      aiAnalysis = result.decisions;
    }

    // 渲染市场分析
    this.renderMarketAnalysis(aiAnalysis);

    // 渲染交易决策
    this.renderTradingDecisions(aiAnalysis);

    // 渲染执行结果
    this.renderExecutionResults(result.executions || []);

    // 渲染最终建议
    this.renderFinalRecommendations(aiAnalysis);
  }

  renderMarketAnalysis(analysis) {
    const content = document.getElementById("marketAnalysisContent");

    if (analysis && analysis.market_analysis) {
      const market = analysis.market_analysis;
      const trendClass =
        market.trend === "上涨"
          ? "bullish"
          : market.trend === "下跌"
          ? "bearish"
          : "sideways";

      content.innerHTML = `
        <div class="trend-info">
          <span class="trend-badge ${trendClass}">${
        market.trend || "未知"
      }</span>
          <span>信心度: ${market.confidence || 0}%</span>
        </div>
        <div class="confidence-bar">
          <div class="confidence-progress">
            <div class="confidence-fill" style="width: ${
              market.confidence || 0
            }%"></div>
          </div>
        </div>
        <p><strong>关键指标:</strong> ${market.key_indicators || "暂无分析"}</p>
      `;
    } else {
      content.innerHTML = `
        <div class="analysis-content">
          <p>AI分析结果格式异常，请查看原始响应。</p>
          <pre style="font-size: 12px; background: var(--bg-3); padding: 8px; border-radius: 4px; overflow-x: auto;">
${JSON.stringify(analysis, null, 2)}
          </pre>
        </div>
      `;
    }
  }

  renderTradingDecisions(analysis) {
    const content = document.getElementById("tradingDecisionsContent");

    if (analysis && analysis.trading_decisions) {
      let decisionsHtml = "";

      for (const [coin, decision] of Object.entries(
        analysis.trading_decisions
      )) {
        const signalClass = decision.signal?.includes("buy")
          ? "buy"
          : decision.signal?.includes("sell")
          ? "sell"
          : "hold";
        const signalText =
          decision.signal === "buy_to_enter"
            ? "开多"
            : decision.signal === "sell_to_enter"
            ? "开空"
            : decision.signal === "close_position"
            ? "平仓"
            : "持有";

        decisionsHtml += `
          <div class="decision-card">
            <div class="decision-header">
              <span class="coin-name">${coin}</span>
              <span class="signal-badge ${signalClass}">${signalText}</span>
            </div>
            <div class="decision-details">
              <div class="detail-item">
                <span class="detail-label">数量:</span>
                <span class="detail-value">${decision.quantity || 0}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">杠杆:</span>
                <span class="detail-value">${decision.leverage || 1}x</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">入场价:</span>
                <span class="detail-value">$${decision.entry_price || 0}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">止盈:</span>
                <span class="detail-value">$${
                  decision.profit_target || 0
                }</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">止损:</span>
                <span class="detail-value">$${decision.stop_loss || 0}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">信心度:</span>
                <span class="detail-value">${Math.round(
                  (decision.confidence || 0) * 100
                )}%</span>
              </div>
            </div>
            <p style="margin-top: 8px; font-size: 12px; color: var(--text-3);">
              <strong>理由:</strong> ${decision.justification || "暂无说明"}
            </p>
          </div>
        `;
      }

      content.innerHTML = decisionsHtml || "<p>暂无交易决策</p>";
    } else {
      // 尝试解析旧格式
      let decisionsHtml = "";
      if (analysis && typeof analysis === "object") {
        for (const [coin, decision] of Object.entries(analysis)) {
          if (decision && typeof decision === "object" && decision.signal) {
            const signalClass = decision.signal?.includes("buy")
              ? "buy"
              : decision.signal?.includes("sell")
              ? "sell"
              : "hold";
            const signalText =
              decision.signal === "buy_to_enter"
                ? "开多"
                : decision.signal === "sell_to_enter"
                ? "开空"
                : decision.signal === "close_position"
                ? "平仓"
                : "持有";

            decisionsHtml += `
              <div class="decision-card">
                <div class="decision-header">
                  <span class="coin-name">${coin}</span>
                  <span class="signal-badge ${signalClass}">${signalText}</span>
                </div>
                <p style="margin-top: 8px; font-size: 12px; color: var(--text-3);">
                  <strong>理由:</strong> ${decision.justification || "暂无说明"}
                </p>
              </div>
            `;
          }
        }
      }

      content.innerHTML = decisionsHtml || "<p>暂无交易决策</p>";
    }
  }

  renderExecutionResults(executions) {
    const content = document.getElementById("executionResultsContent");

    if (executions && executions.length > 0) {
      let executionsHtml = "";

      executions.forEach((execution) => {
        const statusClass = execution.error
          ? "error"
          : execution.message?.includes("成功")
          ? "success"
          : "warning";
        const statusText = execution.error
          ? execution.error
          : execution.message || "执行完成";

        executionsHtml += `
          <div class="execution-item">
            <div class="execution-status ${statusClass}"></div>
            <div class="execution-text">
              <strong>${execution.coin || ""}:</strong> ${statusText}
            </div>
          </div>
        `;
      });

      content.innerHTML = executionsHtml;
    } else {
      content.innerHTML = "<p>暂无执行结果</p>";
    }
  }

  renderFinalRecommendations(analysis) {
    const content = document.getElementById("finalRecommendationsContent");

    if (
      analysis &&
      analysis.final_recommendations &&
      Array.isArray(analysis.final_recommendations)
    ) {
      const recommendationsHtml = analysis.final_recommendations
        .map((rec, index) => `<li>${index + 1}. ${rec}</li>`)
        .join("");

      content.innerHTML = `<ul class="recommendations-list">${recommendationsHtml}</ul>`;
    } else {
      content.innerHTML = "<p>暂无最终建议</p>";
    }
  }

  hideAiTradingModal() {
    const modal = document.getElementById("aiTradingResultModal");
    modal.classList.remove("show");
  }
}

const app = new TradingApp();
