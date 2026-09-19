// Main Application Controller for AI Trading Dashboard
let appState = {
  activeSymbol: "EURUSD",
  activeCategory: "all",
  activeTimeframe: "15m",
  currentPrice: null,
  activeAccount: null,
  allAccounts: [],
  markets: [],
  positions: [],
  history: [],
  aiSettings: {},
  aiStrategies: {},
  aiApiConfig: {},
  recentSignals: [],
  logs: [],
  performance: {}
};

let previousPrices = {};
let ws = null;

// Multi-Chart Grid System
let activeChartLayout = 1; // 1 (1x1), 2 (2x1), 4 (2x2)
let activeFocusedSlot = 0;
let chartSlots = [
  { id: 0, canvasId: "chartCanvas0", tooltipId: "chartTooltip0", engine: null, symbol: "EURUSD", timeframe: "15m" },
  { id: 1, canvasId: "chartCanvas1", tooltipId: "chartTooltip1", engine: null, symbol: "BTCUSDT", timeframe: "15m" },
  { id: 2, canvasId: "chartCanvas2", tooltipId: "chartTooltip2", engine: null, symbol: "XAUUSD", timeframe: "15m" },
  { id: 3, canvasId: "chartCanvas3", tooltipId: "chartTooltip3", engine: null, symbol: "ETHUSDT", timeframe: "15m" },
];
let chartEngine = null; // Pointer for backward compatibility (points to active slot engine)

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  initLiveClock();
  initApp();
  setupEvents();
});

// Live Digital Clock Controller (Local Time & Global UTC Market Time)
function initLiveClock() {
  const timeEl = document.getElementById("clockTimeDigits");
  const tzEl = document.getElementById("clockTzBadge");
  const dateEl = document.getElementById("clockDateText");
  const utcEl = document.getElementById("clockUtcText");

  if (!timeEl) return;

  function updateClock() {
    const now = new Date();

    const hours = String(now.getHours()).padStart(2, "0");
    const mins = String(now.getMinutes()).padStart(2, "0");
    const secs = String(now.getSeconds()).padStart(2, "0");
    timeEl.innerText = `${hours}:${mins}:${secs}`;

    const tzOffset = -now.getTimezoneOffset() / 60;
    let tzLabel = "LOCAL";
    if (tzOffset === 7) tzLabel = "WIB";
    else if (tzOffset === 8) tzLabel = "WITA";
    else if (tzOffset === 9) tzLabel = "WIT";
    else tzLabel = `GMT${tzOffset >= 0 ? '+' : ''}${tzOffset}`;
    if (tzEl) tzEl.innerText = tzLabel;

    const options = { day: "numeric", month: "short", year: "numeric" };
    if (dateEl) dateEl.innerText = now.toLocaleDateString("id-ID", options);

    const utcHours = String(now.getUTCHours()).padStart(2, "0");
    const utcMins = String(now.getUTCMinutes()).padStart(2, "0");
    if (utcEl) utcEl.innerText = `UTC ${utcHours}:${utcMins}`;
  }

  updateClock();
  setInterval(updateClock, 1000);
}

async function initApp() {
  await fetchFullState();
  initMultiChartSystem();
  initWebSocket();
}

// 1. Data Fetching
async function fetchFullState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    
    appState.activeAccount = data.active_account;
    appState.allAccounts = data.all_accounts;
    appState.markets = data.markets;
    appState.positions = data.open_positions;
    appState.history = data.history;
    appState.aiSettings = data.ai_settings;
    appState.aiStrategies = data.ai_strategies;
    appState.aiApiConfig = data.ai_api_config || {};
    appState.recentSignals = data.recent_signals;
    appState.logs = data.logs;
    appState.performance = data.performance;
    appState.circuitBreaker = data.circuit_breaker || null;
    appState.aiLearning = data.ai_learning || null;

    renderAll();
  } catch (err) {
    console.error("Gagal mengambil state aplikasi:", err);
  }
}

// ==========================================================================
// MULTI-CHART GRID ENGINE CONTROLLER
// ==========================================================================
function initMultiChartSystem() {
  // Populate dropdowns for all 4 slots
  chartSlots.forEach((slot, idx) => {
    const sel = document.getElementById(`slotSymbolSelect${idx}`);
    if (sel && appState.markets && appState.markets.length > 0) {
      sel.innerHTML = appState.markets.map(m => `
        <option value="${m.symbol}" ${m.symbol === slot.symbol ? 'selected' : ''}>${m.symbol} - ${m.name}</option>
      `).join("");

      sel.addEventListener("change", (e) => {
        onSlotSymbolChanged(idx, e.target.value);
      });
    }

    // Sub-timeframe buttons
    const tfContainer = document.querySelector(`.subchart-tf-group[data-slot="${idx}"]`);
    if (tfContainer) {
      tfContainer.querySelectorAll(".sub-tf-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          onSlotTimeframeChanged(idx, btn.dataset.tf);
        });
      });
    }

    // Clicking anywhere on slot focuses it
    const card = document.getElementById(`chartSlot${idx}`);
    if (card) {
      card.addEventListener("click", () => {
        focusChartSlot(idx);
      });
    }
  });

  // Setup Layout Switcher buttons
  document.querySelectorAll(".layout-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const layout = parseInt(btn.dataset.layout);
      setChartLayout(layout);
      window.soundFx?.playClick();
    });
  });

  // Start with Layout 1 (single)
  setChartLayout(1);
}

function setChartLayout(layoutMode) {
  activeChartLayout = layoutMode;

  // Update layout button states
  document.querySelectorAll(".layout-btn").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.layout) === layoutMode);
  });

  // Update container grid class
  const grid = document.getElementById("multiChartGrid");
  if (grid) {
    grid.className = `multi-chart-grid layout-${layoutMode}`;
  }

  // If currently focused slot is out of bounds, reset focus to slot 0
  if (activeFocusedSlot >= layoutMode) {
    focusChartSlot(0);
  }

  // Show/hide cards and load or resize engines
  chartSlots.forEach((slot, idx) => {
    const card = document.getElementById(`chartSlot${idx}`);
    if (!card) return;

    if (idx < layoutMode) {
      card.style.display = "flex";
      if (!slot.engine) {
        loadSlotChart(idx, slot.symbol, slot.timeframe);
      } else {
        setTimeout(() => {
          slot.engine.resize();
        }, 50);
      }
    } else {
      card.style.display = "none";
    }
  });

  // Extra resize pass after transition finishes
  setTimeout(() => {
    chartSlots.forEach((slot, idx) => {
      if (idx < layoutMode && slot.engine) {
        slot.engine.resize();
      }
    });
  }, 150);
}

function focusChartSlot(slotIdx) {
  if (slotIdx >= activeChartLayout) return;
  activeFocusedSlot = slotIdx;
  const slot = chartSlots[slotIdx];
  if (!slot) return;

  appState.activeSymbol = slot.symbol;
  appState.activeTimeframe = slot.timeframe;
  chartEngine = slot.engine;

  // Update visual focus class on cards
  document.querySelectorAll(".subchart-card").forEach((card, idx) => {
    card.classList.toggle("active-focus", idx === slotIdx);
  });

  const pInfo = appState.markets.find(m => m.symbol === slot.symbol);
  if (pInfo) {
    updateActiveSymbolHeader(pInfo);
    renderQuickOrderPrices();
  }

  syncHeaderTimeframeButtons(slot.timeframe);
  renderTickerStrip();
}

function onSlotSymbolChanged(slotIdx, newSymbol) {
  const slot = chartSlots[slotIdx];
  if (!slot) return;
  loadSlotChart(slotIdx, newSymbol, slot.timeframe);
  focusChartSlot(slotIdx);
}

function onSlotTimeframeChanged(slotIdx, newTf) {
  const slot = chartSlots[slotIdx];
  if (!slot) return;
  slot.timeframe = newTf;
  const tfGroup = document.querySelector(`.subchart-tf-group[data-slot="${slotIdx}"]`);
  if (tfGroup) {
    tfGroup.querySelectorAll(".sub-tf-btn").forEach(b => b.classList.toggle("active", b.dataset.tf === newTf));
  }
  loadSlotChart(slotIdx, slot.symbol, newTf);
  if (slotIdx === activeFocusedSlot) {
    syncHeaderTimeframeButtons(newTf);
  }
}

function syncHeaderTimeframeButtons(tf) {
  document.querySelectorAll("#headerTimeframeGroup .tf-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tf === tf);
  });
}

function updateSlotHeaderLive(slotIdx, info) {
  if (!info) return;
  const priceEl = document.getElementById(`slotPrice${slotIdx}`);
  const changeEl = document.getElementById(`slotChange${slotIdx}`);
  const digits = info.digits || (info.symbol?.includes("JPY") ? 3 : info.symbol?.includes("USDT") ? 2 : 5);
  
  if (priceEl && info.last !== undefined) {
    priceEl.innerText = info.last.toFixed(digits);
  }
  if (changeEl && (info.change24h !== undefined || info.change_24h !== undefined)) {
    const val = info.change24h !== undefined ? info.change24h : info.change_24h;
    const isUp = val >= 0;
    changeEl.innerText = `${isUp ? '+' : ''}${val.toFixed(2)}%`;
    changeEl.style.color = isUp ? "var(--neon-green)" : "var(--neon-red)";
  }
}

async function loadSlotChart(slotIdx, symbol, timeframe) {
  try {
    const slot = chartSlots[slotIdx];
    if (!slot) return;

    slot.symbol = symbol;
    slot.timeframe = timeframe;

    if (slotIdx === activeFocusedSlot) {
      appState.activeSymbol = symbol;
      appState.activeTimeframe = timeframe;
    }

    if (!slot.engine) {
      slot.engine = new TradingChartEngine(slot.canvasId, slot.tooltipId);
    }
    if (slotIdx === activeFocusedSlot || slotIdx === 0) {
      chartEngine = slot.engine;
    }

    // Sync select dropdown
    const sel = document.getElementById(`slotSymbolSelect${slotIdx}`);
    if (sel && sel.value !== symbol) {
      sel.value = symbol;
    }

    // Sync sub-tf buttons
    const tfGroup = document.querySelector(`.subchart-tf-group[data-slot="${slotIdx}"]`);
    if (tfGroup) {
      tfGroup.querySelectorAll(".sub-tf-btn").forEach(b => {
        b.classList.toggle("active", b.dataset.tf === timeframe);
      });
    }

    const res = await fetch(`/api/candles?symbol=${symbol}&timeframe=${timeframe}`);
    const data = await res.json();

    const pInfo = appState.markets.find(m => m.symbol === symbol);
    const digits = data.info?.digits || (symbol.includes("JPY") ? 3 : symbol.includes("USDT") ? 2 : 5);

    // Filter open positions for marker plotting
    const activeMarkers = appState.positions.filter(p => p.symbol === symbol);

    slot.engine.setData(data.candles, symbol, digits, activeMarkers);
    slot.engine.resize();

    updateSlotHeaderLive(slotIdx, pInfo || data.info);

    if (slotIdx === activeFocusedSlot) {
      updateActiveSymbolHeader(pInfo || data.info);
      renderQuickOrderPrices();
      syncHeaderTimeframeButtons(timeframe);
    }
  } catch (err) {
    console.error(`Gagal memuat candles untuk slot ${slotIdx}:`, err);
  }
}

async function loadSymbolData(symbol, timeframe) {
  await loadSlotChart(activeFocusedSlot, symbol, timeframe);
}

// 2. WebSocket Realtime Sync
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/api/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("wsStatusDot").style.background = "#00f090";
    document.getElementById("wsStatusText").innerText = "LIVE STREAM";
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "tick_update") {
        handleTickUpdate(data);
      }
    } catch (e) {
      console.error("WS Parse Error:", e);
    }
  };

  ws.onclose = () => {
    document.getElementById("wsStatusDot").style.background = "#ff3366";
    document.getElementById("wsStatusText").innerText = "RECONNECTING";
    setTimeout(initWebSocket, 3000);
  };
}

function handleTickUpdate(data) {
  // Update state
  if (data.prices) {
    appState.markets = data.prices;
    renderTickerStrip();

    // Broadcast live prices to all active visible chart slots
    chartSlots.forEach((slot, idx) => {
      if (idx >= activeChartLayout) return;
      const p = data.prices.find(item => item.symbol === slot.symbol);
      if (p) {
        if (slot.engine) slot.engine.updateLivePrice(p.last);
        updateSlotHeaderLive(idx, p);
      }
    });

    // If active focused symbol updated, update quick order & header
    const current = data.prices.find(p => p.symbol === appState.activeSymbol);
    if (current) {
      updateActiveSymbolHeader(current);
      renderQuickOrderPrices();
    }
  }

  if (data.active_account) {
    appState.activeAccount = data.active_account;
    renderAccountBadge();
    renderAccountMetrics();
  }

  if (data.open_positions) {
    appState.positions = data.open_positions;
    renderPositionsTable();
  }

  if (data.performance) {
    appState.performance = data.performance;
    renderPerformanceStats();
  }

  if (data.recent_logs) {
    appState.logs = data.recent_logs;
    renderLogs();
  }

  if (data.recent_signals) {
    appState.recentSignals = data.recent_signals;
    renderAISignals();
  }

  if (data.circuit_breaker) {
    appState.circuitBreaker = data.circuit_breaker;
    renderCircuitBreakerStatus(data.circuit_breaker);
  }

  if (data.ai_learning) {
    appState.aiLearning = data.ai_learning;
    renderAILearningStats(data.ai_learning);
  }
}

// 3. UI Renderers
function renderAll() {
  renderAccountBadge();
  renderTickerStrip();
  renderAISettingsUI();
  renderAIBrainBadge();
  renderAISignals();
  renderAccountMetrics();
  renderPositionsTable();
  renderHistoryTable();
  renderPerformanceStats();
  renderLogs();
  renderCircuitBreakerStatus(appState.circuitBreaker);
  renderAILearningStats(appState.aiLearning);
}

function renderAILearningStats(lrn) {
  if (!lrn) return;

  // Navbar pill
  const navLvl = document.getElementById("navBrainLevelText");
  const navXp = document.getElementById("navBrainXpTag");
  if (navLvl) navLvl.innerText = `AI: LVL ${lrn.brain_level}`;
  if (navXp) navXp.innerText = `${lrn.experience_points} XP`;

  // Analytics Card
  const statLvl = document.getElementById("statBrainLevel");
  const statXp = document.getElementById("statBrainXp");
  if (statLvl) statLvl.innerText = `Tingkat ${lrn.brain_level}`;
  if (statXp) statXp.innerText = `XP: ${lrn.experience_points} / ${lrn.next_level_xp}`;

  // Strategy Weights
  const weightsList = document.getElementById("aiStrategyWeightsList");
  if (weightsList && lrn.strategy_weights) {
    const stratNames = {
      "neural_momentum": "Neural Momentum Trend",
      "smart_money": "Smart Money Concepts",
      "mean_reversion": "AI Mean Reversion",
      "neural_scalper": "Neural Scalper"
    };
    weightsList.innerHTML = Object.entries(lrn.strategy_weights).map(([k, w]) => {
      let statusClass = "neutral";
      let statusText = "Normal";
      let color = "var(--text-primary)";
      if (w > 1.0) {
        statusClass = "boosted";
        statusText = "Ditingkatkan";
        color = "var(--neon-green)";
      } else if (w < 1.0) {
        statusClass = "penalized";
        statusText = "Ditekan (Proteksi)";
        color = "var(--neon-red)";
      }
      return `<div class="weight-row ${statusClass}">
        <span>${stratNames[k] || k}</span>
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:0.7rem; color:var(--text-muted);">${statusText}</span>
          <span class="weight-val-badge" style="color:${color};">${w.toFixed(2)}x</span>
        </div>
      </div>`;
    }).join("");
  }

  // Insights Terminal
  const insightsTerm = document.getElementById("aiInsightsTerminal");
  if (insightsTerm && lrn.recent_insights) {
    if (lrn.recent_insights.length === 0) {
      insightsTerm.innerHTML = '<div style="color:var(--text-muted); font-size:0.75rem; text-align:center; padding:10px;">Belum ada catatan transaksi yang dipelajari. AI akan mencatat otomatis saat posisi ditutup.</div>';
    } else {
      insightsTerm.innerHTML = lrn.recent_insights.map(ins => {
        const typeClass = ins.type || "neutral";
        return `<div class="insight-row ${typeClass}">
          <div style="display:flex; justify-content:space-between; font-size:0.7rem; color:var(--text-muted); margin-bottom:2px;">
            <span>${ins.strategy ? `<b>[${ins.strategy}]</b> ${ins.symbol || ''}` : 'SISTEM AI'}</span>
            <span>${ins.timestamp || ''}</span>
          </div>
          <div>${ins.message}</div>
        </div>`;
      }).join("");
    }
  }
}

function renderCircuitBreakerStatus(cb) {
  if (!cb) return;
  const pill = document.getElementById("navCircuitBreakerBadge");
  const text = document.getElementById("navCbText");
  const banner = document.getElementById("circuitBreakerBanner");
  const reason = document.getElementById("cbBannerReason");

  if (cb.tripped) {
    if (pill) {
      pill.className = "circuit-breaker-pill tripped";
      if (text) text.innerText = "🚨 CB: TERPICU (LOCKED)";
    }
    if (banner) {
      banner.style.display = "block";
      if (reason && cb.reason) reason.innerText = cb.reason;
    }
  } else {
    if (pill) {
      pill.className = "circuit-breaker-pill safe";
      const lossPct = (cb.daily_loss_pct || 0).toFixed(2);
      if (text) text.innerText = `CB: AMAN (DD: ${lossPct}%)`;
    }
    if (banner) {
      banner.style.display = "none";
    }
  }
}

function formatCurrency(val, currency = "USD") {
  const num = Number(val) || 0;
  if (currency === "IDR") {
    return `Rp ${Math.round(num).toLocaleString('id-ID')}`;
  }
  if (currency === "USDT") {
    return `${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT`;
  }
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function renderAccountBadge() {
  const acc = appState.activeAccount;
  if (!acc) return;

  const nameEl = document.getElementById("activeAccName");
  const typeEl = document.getElementById("activeAccType");
  const balEl = document.getElementById("activeAccBalance");

  if (nameEl) nameEl.innerText = acc.name;
  if (typeEl) {
    if (acc.mode === "real") {
      typeEl.innerText = `REAL [${acc.type.toUpperCase()}]`;
      typeEl.className = "acc-type-tag real";
    } else {
      typeEl.innerText = acc.type.toUpperCase();
      typeEl.className = `acc-type-tag ${acc.type}`;
    }
  }
  if (balEl) balEl.innerText = formatCurrency(acc.balance, acc.currency);
}


function renderTickerStrip() {
  const container = document.getElementById("tickerStrip");
  if (!container) return;

  const filtered = appState.markets.filter(m => {
    if (appState.activeCategory === "all") return true;
    return m.category === appState.activeCategory;
  });

  container.innerHTML = filtered.map(m => {
    const isUp = m.change24h >= 0;
    const prev = previousPrices[m.symbol];
    let flashClass = "";
    if (prev) {
      if (m.last > prev) flashClass = "flash-up";
      else if (m.last < prev) flashClass = "flash-down";
    }
    previousPrices[m.symbol] = m.last;

    const isActive = m.symbol === appState.activeSymbol ? "active" : "";

    return `
      <div class="ticker-card ${isActive} ${flashClass}" onclick="selectSymbol('${m.symbol}')">
        <div>
          <div class="ticker-sym">${m.symbol}</div>
          <div class="ticker-cat">${m.category}</div>
        </div>
        <div class="ticker-price-wrap">
          <div class="ticker-price ${isUp ? 'up' : 'down'}">${m.last.toFixed(m.digits)}</div>
          <div class="ticker-change ${isUp ? 'up' : 'down'}">${isUp ? '+' : ''}${m.change24h}%</div>
        </div>
      </div>
    `;
  }).join("");
}

function updateActiveSymbolHeader(info) {
  if (!info) return;
  const symBadge = document.getElementById("headerSymbolBadge");
  const nameLabel = document.getElementById("headerSymbolName");
  const bidEl = document.getElementById("headerLiveBid");
  const askEl = document.getElementById("headerLiveAsk");
  const spreadEl = document.getElementById("headerSpread");

  if (symBadge) symBadge.innerText = info.symbol;
  if (nameLabel) nameLabel.innerText = info.name || "";
  if (bidEl) bidEl.innerText = info.bid?.toFixed(info.digits) || "-";
  if (askEl) askEl.innerText = info.ask?.toFixed(info.digits) || "-";

  if (spreadEl && info.ask && info.bid) {
    const spread = Math.abs(info.ask - info.bid);
    spreadEl.innerText = `Spread: ${spread.toFixed(info.digits)}`;
  }
}

function renderQuickOrderPrices() {
  const info = appState.markets.find(m => m.symbol === appState.activeSymbol);
  if (!info) return;
  const buyP = document.getElementById("quickBuyPrice");
  const sellP = document.getElementById("quickSellPrice");

  if (buyP) buyP.innerText = `@ ${info.ask.toFixed(info.digits)}`;
  if (sellP) sellP.innerText = `@ ${info.bid.toFixed(info.digits)}`;
}

function renderAISettingsUI() {
  const s = appState.aiSettings;
  const masterBtn = document.getElementById("aiMasterToggle");
  const stratSelect = document.getElementById("aiStrategySelect");
  const confSlider = document.getElementById("aiConfidenceSlider");
  const confVal = document.getElementById("aiConfidenceVal");
  const riskInput = document.getElementById("aiRiskInput");
  const statusBadge = document.getElementById("aiStatusPill");

  if (masterBtn) {
    if (s.mode === "auto") {
      masterBtn.className = "ai-master-toggle-btn active";
      masterBtn.innerHTML = `
        <span class="pulse-dot"></span>
        <span>ROBOT AI: AKTIF</span>
      `;
      if (statusBadge) {
        statusBadge.className = "ai-status-indicator online";
        statusBadge.innerHTML = `<span class="pulse-dot"></span> BERJALAN`;
      }
    } else {
      masterBtn.className = "ai-master-toggle-btn paused";
      masterBtn.innerHTML = `
        <span class="pulse-dot" style="background:#64748b"></span>
        <span>ROBOT AI: PAUSED</span>
      `;
      if (statusBadge) {
        statusBadge.className = "ai-status-indicator paused";
        statusBadge.innerHTML = `<span class="pulse-dot" style="background:#ffb703"></span> NONAKTIF`;
      }
    }
  }

  // Populate strategies
  if (stratSelect && appState.aiStrategies) {
    stratSelect.innerHTML = Object.values(appState.aiStrategies).map(strat => `
      <option value="${strat.id}" ${strat.id === s.active_strategy ? 'selected' : ''}>
        ${strat.name} (R:R 1:${strat.min_rr})
      </option>
    `).join("");
  }

  if (confSlider && confVal) {
    confSlider.value = s.confidence_threshold || 75;
    confVal.innerText = `${confSlider.value}%`;
  }

  if (riskInput) {
    riskInput.value = s.risk_per_trade_pct || 2.0;
  }
}

function renderAIBrainBadge() {
  const cfg = appState.aiApiConfig?.config || {};
  const modelEl = document.getElementById("aiActiveModelBadge");
  const providerEl = document.getElementById("aiActiveProviderBadge");
  if (!modelEl || !providerEl) return;

  if (cfg.enabled && (cfg.api_key || cfg.provider === "ollama")) {
    const pName = (cfg.provider || "CLOUD").toUpperCase();
    modelEl.innerText = `${cfg.model || 'Custom LLM'}`;
    modelEl.style.color = "var(--neon-green)";
    providerEl.innerText = pName;
    providerEl.className = "acc-type-tag";
  } else {
    modelEl.innerText = "Algoritma Lokal (Built-in)";
    modelEl.style.color = "var(--neon-cyan)";
    providerEl.innerText = "HEURISTIC";
    providerEl.className = "acc-type-tag mt5";
  }
}

function renderAISignals() {
  const container = document.getElementById("aiSignalsTerminal");
  if (!container) return;

  if (!appState.recentSignals || appState.recentSignals.length === 0) {
    container.innerHTML = `
      <div style="color:var(--text-muted); text-align:center; padding: 20px;">
        🤖 Menunggu pemindaian sinyal AI berikutnya...
      </div>
    `;
    return;
  }

  container.innerHTML = appState.recentSignals.map(sig => {
    const isBuy = sig.direction === "BUY";
    const date = new Date(sig.timestamp * 1000).toLocaleTimeString();
    return `
      <div class="reason-entry ${isBuy ? 'buy' : 'sell'}">
        <div class="reason-head">
          <span class="reason-sym">${sig.symbol} [${sig.direction}]</span>
          <span class="reason-conf">${sig.confidence}% CONF</span>
        </div>
        <div class="reason-desc">
          <b>${sig.strategy}</b> • SL: ${sig.sl} | TP: ${sig.tp}
          <br>
          ${sig.reasoning ? sig.reasoning.join(" • ") : sig.summary_text}
        </div>
      </div>
    `;
  }).join("");
}

function renderAccountMetrics() {
  const acc = appState.activeAccount;
  if (!acc) return;
  const curr = acc.currency || "USD";

  document.getElementById("metricBalance").innerText = formatCurrency(acc.balance, curr);
  document.getElementById("metricEquity").innerText = formatCurrency(acc.equity, curr);
  document.getElementById("metricMargin").innerText = formatCurrency(acc.margin, curr);
  document.getElementById("metricFreeMargin").innerText = formatCurrency(acc.free_margin, curr);
  document.getElementById("metricMarginLevel").innerText = acc.margin > 0 ? `${acc.margin_level.toFixed(1)}%` : "0.0%";
  document.getElementById("metricLeverage").innerText = `1:${acc.leverage}`;
}

function renderPositionsTable() {
  const tbody = document.getElementById("positionsTableBody");
  const counter = document.getElementById("positionsCounter");
  if (!tbody) return;

  if (counter) counter.innerText = appState.positions.length;

  if (appState.positions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" style="text-align:center; color:var(--text-muted); padding:30px;">
          Tidak ada posisi trading yang terbuka. Nyalakan Robot AI atau lakukan Buy/Sell manual.
        </td>
      </tr>
    `;
    return;
  }

  const curr = appState.activeAccount?.currency || "USD";

  tbody.innerHTML = appState.positions.map(p => {
    const isBuy = p.direction === "BUY";
    const isProfit = p.pnl >= 0;
    const cfg = appState.markets.find(m => m.symbol === p.symbol);
    const digits = cfg?.digits || 2;

    let badgeHtml = `<span class="tag-badge ${p.is_ai ? 'tag-ai' : ''}">${p.is_ai ? 'AI ROBOT' : 'MANUAL'}</span>`;
    if (p.ticket) {
      badgeHtml += ` <span class="tag-badge" style="background:rgba(0,240,144,0.15); color:#00f090; font-size:0.68rem;" title="Order Terverifikasi Broker MT5">#${p.ticket}</span>`;
    }

    return `
      <tr>
        <td>${badgeHtml}</td>
        <td><b>${p.symbol}</b></td>
        <td><span class="tag-badge ${isBuy ? 'tag-buy' : 'tag-sell'}">${p.direction}</span></td>
        <td>${p.lot}</td>
        <td>${p.entry_price.toFixed(digits)}</td>
        <td>${p.current_price.toFixed(digits)}</td>
        <td style="color:#ff3366">${p.sl ? p.sl.toFixed(digits) : '-'}</td>
        <td style="color:#00f090">${p.tp ? p.tp.toFixed(digits) : '-'}</td>
        <td class="${isProfit ? 'up' : 'down'}" style="font-weight:700;">
          ${isProfit ? '+' : ''}${formatCurrency(p.pnl, curr)}
        </td>
        <td>
          <button class="btn-action-edit" onclick="openModifyModal('${p.id}', ${p.sl}, ${p.tp}, '${p.symbol}')">Edit</button>
          <button class="btn-action-close" onclick="closeOrder('${p.id}')">Close</button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderHistoryTable() {
  const tbody = document.getElementById("historyTableBody");
  const counter = document.getElementById("historyCounter");
  if (!tbody) return;

  if (counter) counter.innerText = appState.history.length;

  if (appState.history.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" style="text-align:center; color:var(--text-muted); padding:25px;">
          Belum ada riwayat transaksi yang ditutup.
        </td>
      </tr>
    `;
    return;
  }

  const curr = appState.activeAccount?.currency || "USD";

  tbody.innerHTML = appState.history.map(h => {
    const isProfit = h.pnl >= 0;
    const date = new Date(h.close_time * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const cfg = appState.markets.find(m => m.symbol === h.symbol);
    const digits = cfg?.digits || 2;

    return `
      <tr>
        <td><span class="tag-badge ${h.is_ai ? 'tag-ai' : ''}">${h.is_ai ? 'AI' : 'MAN'}</span></td>
        <td><b>${h.symbol}</b></td>
        <td><span class="tag-badge ${h.direction === 'BUY' ? 'tag-buy' : 'tag-sell'}">${h.direction}</span></td>
        <td>${h.lot}</td>
        <td>${h.entry_price.toFixed(digits)}</td>
        <td>${h.exit_price.toFixed(digits)}</td>
        <td class="${isProfit ? 'up' : 'down'}" style="font-weight:700;">
          ${isProfit ? '+' : ''}${formatCurrency(h.pnl, curr)}
        </td>
        <td><span style="font-size:0.7rem; color:var(--text-secondary)">${h.close_reason || 'Closed'}</span></td>
        <td style="color:var(--text-muted)">${date}</td>
      </tr>
    `;
  }).join("");
}


function renderPerformanceStats() {
  const p = appState.performance;
  if (!p) return;

  const winRateEl = document.getElementById("statWinRate");
  const totalPnlEl = document.getElementById("statTotalPnl");
  const pfEl = document.getElementById("statProfitFactor");
  const ddEl = document.getElementById("statMaxDrawdown");
  const tradesCountEl = document.getElementById("statTotalTrades");

  if (winRateEl) winRateEl.innerText = `${p.win_rate || 0}%`;
  if (totalPnlEl) {
    const isUp = (p.total_pnl || 0) >= 0;
    totalPnlEl.className = `metric-value ${isUp ? 'up' : 'down'}`;
    totalPnlEl.innerText = `${isUp ? '+' : ''}$${(p.total_pnl || 0).toFixed(2)}`;
  }
  if (pfEl) pfEl.innerText = p.profit_factor || "0.0";
  if (ddEl) ddEl.innerText = `${p.max_drawdown || 0}%`;
  if (tradesCountEl) tradesCountEl.innerText = `${p.win_trades || 0}W / ${p.loss_trades || 0}L (${p.total_trades || 0} Total)`;

  renderEquityChart(p.equity_curve || []);
}

function renderEquityChart(curve) {
  const canvas = document.getElementById("equityChart");
  if (!canvas || curve.length === 0) return;
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;

  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;

  ctx.fillStyle = "#090d16";
  ctx.fillRect(0, 0, w, h);

  const vals = curve.map(c => c.v);
  const minV = Math.min(...vals) * 0.99;
  const maxV = Math.max(...vals) * 1.01;
  const range = maxV - minV || 1;

  ctx.strokeStyle = "#00f090";
  ctx.lineWidth = 2;
  ctx.beginPath();

  curve.forEach((pt, i) => {
    const x = (i / (curve.length - 1)) * (w - 20) + 10;
    const y = h - ((pt.v - minV) / range) * (h - 30) - 15;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Draw fill
  ctx.lineTo(w - 10, h);
  ctx.lineTo(10, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgba(0, 240, 144, 0.25)");
  grad.addColorStop(1, "rgba(0, 240, 144, 0.0)");
  ctx.fillStyle = grad;
  ctx.fill();
}

function renderLogs() {
  const container = document.getElementById("systemLogsTerminal");
  if (!container) return;

  container.innerHTML = appState.logs.map(log => `
    <div class="log-line">
      <span class="log-time">[${log.time}]</span>
      <span class="log-msg ${log.level}">${log.message}</span>
    </div>
  `).join("");
}

// 4. Interactive Event Handlers
function setupEvents() {
  // 1-Screen Pro Mode Toggle
  const btnToggleScreen = document.getElementById("btnToggleScreenMode");
  if (btnToggleScreen) {
    const savedMode = localStorage.getItem("apexai_screen_mode");
    if (savedMode === "scroll") {
      document.body.classList.remove("pro-fit-screen");
      btnToggleScreen.classList.remove("active");
      const icon = document.getElementById("screenModeIcon");
      const text = document.getElementById("screenModeText");
      if (icon) icon.innerText = "📜";
      if (text) text.innerText = "Mode Scroll";
    }

    btnToggleScreen.addEventListener("click", () => {
      const isNowFit = document.body.classList.toggle("pro-fit-screen");
      btnToggleScreen.classList.toggle("active", isNowFit);
      const icon = document.getElementById("screenModeIcon");
      const text = document.getElementById("screenModeText");
      if (icon) icon.innerText = isNowFit ? "🖥️" : "📜";
      if (text) text.innerText = isNowFit ? "1 Layar (Fit)" : "Mode Scroll";

      localStorage.setItem("apexai_screen_mode", isNowFit ? "fit" : "scroll");
      window.soundFx?.playClick();

      // Trigger resize on all active chart engines
      setTimeout(() => {
        chartSlots.forEach((s, idx) => {
          if (idx < activeChartLayout && s.engine) {
            s.engine.resize();
          }
        });
      }, 80);
    });
  }

  // Category filter tabs
  document.querySelectorAll(".market-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".market-tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      appState.activeCategory = btn.dataset.category;
      renderTickerStrip();
      window.soundFx?.playClick();
    });
  });

  // Header Timeframe buttons (controls active focused slot)
  document.querySelectorAll("#headerTimeframeGroup .tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#headerTimeframeGroup .tf-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      onSlotTimeframeChanged(activeFocusedSlot, btn.dataset.tf);
      window.soundFx?.playClick();
    });
  });

  // Bottom Tabs navigation
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content-pane").forEach(p => p.style.display = "none");

      btn.classList.add("active");
      const targetPane = document.getElementById(btn.dataset.target);
      if (targetPane) targetPane.style.display = "block";
      if (btn.dataset.target === "paneBacktest" && backtestEquityData.length > 0) {
        setTimeout(() => drawBacktestEquityChart(backtestEquityData), 50);
      }
      window.soundFx?.playClick();
    });
  });

  // Quick Buy & Sell
  document.getElementById("quickBuyBtn")?.addEventListener("click", () => executeQuickTrade("BUY"));
  document.getElementById("quickSellBtn")?.addEventListener("click", () => executeQuickTrade("SELL"));

  // AI Master Toggle
  document.getElementById("aiMasterToggle")?.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/ai/toggle", { method: "POST" });
      const data = await res.json();
      appState.aiSettings.mode = data.mode;
      renderAISettingsUI();
      window.soundFx?.playAlert();
    } catch (e) {
      console.error(e);
    }
  });

  // AI Strategy Select
  document.getElementById("aiStrategySelect")?.addEventListener("change", (e) => {
    updateAISetting({ active_strategy: e.target.value });
  });

  // Confidence Slider
  const slider = document.getElementById("aiConfidenceSlider");
  if (slider) {
    slider.addEventListener("input", (e) => {
      document.getElementById("aiConfidenceVal").innerText = `${e.target.value}%`;
    });
    slider.addEventListener("change", (e) => {
      updateAISetting({ confidence_threshold: parseInt(e.target.value) });
    });
  }

  // Risk % input
  document.getElementById("aiRiskInput")?.addEventListener("change", (e) => {
    updateAISetting({ risk_per_trade_pct: parseFloat(e.target.value) });
  });

  // Scan Now Button
  document.getElementById("aiScanNowBtn")?.addEventListener("click", async () => {
    window.soundFx?.playClick();
    try {
      const res = await fetch("/api/ai/scan-now", { method: "POST" });
      const data = await res.json();
      if (data.recent_signals) {
        appState.recentSignals = data.recent_signals;
        renderAISignals();
      }
    } catch (e) {
      console.error(e);
    }
  });

  // Close All Button
  document.getElementById("closeAllBtn")?.addEventListener("click", async () => {
    if (confirm("Tutup SEMUA posisi aktif saat ini?")) {
      await fetch("/api/order/close-all", { method: "POST" });
      window.soundFx?.playAlert();
    }
  });

  // Emergency Kill-Switch Button
  document.getElementById("killSwitchBtn")?.addEventListener("click", async () => {
    const ok = confirm("⚠️ PERINGATAN DARURAT (EMERGENCY KILL-SWITCH)!\n\nApakah Anda yakin ingin memicu Kill-Switch?\n• Semua posisi aktif akan segera DITUTUP paksa.\n• Robot AI akan langsung DIMATIKAN.\n• Circuit Breaker akan dikunci.");
    if (!ok) return;

    try {
      const res = await fetch("/api/risk/kill-switch", { method: "POST" });
      const data = await res.json();
      window.soundFx?.playAlert();
      await fetchFullState();
      alert(`🛑 EMERGENCY KILL-SWITCH DIAKTIFKAN!\n${data.message}`);
    } catch (e) {
      console.error(e);
      alert("Gagal memicu Kill-Switch: " + e.message);
    }
  });

  // Circuit Breaker Reset Button
  document.getElementById("btnResetCircuitBreaker")?.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/risk/circuit-breaker/reset", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        window.soundFx?.playClick();
        await fetchFullState();
      }
    } catch (e) {
      console.error("Gagal reset circuit breaker:", e);
    }
  });

  // Reset AI Memory Button
  document.getElementById("btnResetAiMemory")?.addEventListener("click", async () => {
    if (confirm("Reset seluruh memori pembelajaran AI kembali ke Level 1 bawaan?")) {
      try {
        const res = await fetch("/api/ai/learning/reset", { method: "POST" });
        const data = await res.json();
        if (data.success) {
          window.soundFx?.playAlert();
          await fetchFullState();
        }
      } catch (e) {
        console.error("Gagal reset memori AI:", e);
      }
    }
  });

  // Backtest Confidence Slider
  const btConfSlider = document.getElementById("btConfidence");
  if (btConfSlider) {
    btConfSlider.addEventListener("input", (e) => {
      const valEl = document.getElementById("btConfidenceVal");
      if (valEl) valEl.innerText = `${e.target.value}%`;
    });
  }

  // Backtest Form Submit
  document.getElementById("backtestForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btnRunBacktest");
    const origText = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = "⏳ Menjalankan Simulasi AI...";
    }

    const symbol = document.getElementById("btSymbol").value;
    const strategy = document.getElementById("btStrategy").value;
    const initialBalance = parseFloat(document.getElementById("btInitialBalance").value);
    const riskPct = parseFloat(document.getElementById("btRiskPct").value);
    const confidence = parseInt(document.getElementById("btConfidence").value);

    try {
      const res = await fetch("/api/ai/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol,
          strategy_id: strategy,
          initial_balance: initialBalance,
          risk_pct: riskPct,
          confidence_threshold: confidence
        })
      });
      const result = await res.json();
      if (result.success) {
        renderBacktestResults(result);
        window.soundFx?.playOrderSuccess();
      } else {
        alert("Simulasi backtest gagal: " + (result.message || "Unknown error"));
      }
    } catch (err) {
      console.error("Backtest error:", err);
      alert("Koneksi backtest error: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origText;
      }
    }
  });

  // Account Switcher Modal Triggers
  document.getElementById("accountSelectorBtn")?.addEventListener("click", () => openAccountModal());
  document.getElementById("closeAccountModalBtn")?.addEventListener("click", () => closeAccountModal());
  document.getElementById("closeModifyModalBtn")?.addEventListener("click", () => closeModifyModal());

  // AI API Config Modal Triggers
  document.getElementById("openAIConfigBtn")?.addEventListener("click", () => openAIConfigModal());
  document.getElementById("closeAIConfigModalBtn")?.addEventListener("click", () => closeAIConfigModal());
  document.getElementById("btnToggleApiKeyVis")?.addEventListener("click", () => toggleApiKeyVisibility());
  document.getElementById("cfgAIProvider")?.addEventListener("change", (e) => applyAIProviderPreset(e.target.value));
  document.getElementById("btnTestAIConnection")?.addEventListener("click", () => testAIConnectionAction());
  document.getElementById("aiConfigForm")?.addEventListener("submit", (e) => saveAIConfigAction(e));

  // Real Broker Connect Modal Triggers
  document.getElementById("btnOpenConnectRealModal")?.addEventListener("click", () => openConnectRealModal());
  document.getElementById("closeConnectRealModalBtn")?.addEventListener("click", () => closeConnectRealModal());
  document.getElementById("btnToggleMT5Pass")?.addEventListener("click", () => togglePasswordVisibility("realMT5Password", "btnToggleMT5Pass"));
  document.getElementById("btnToggleCryptoSecret")?.addEventListener("click", () => togglePasswordVisibility("realCryptoApiSecret", "btnToggleCryptoSecret"));
  document.getElementById("realMT5Form")?.addEventListener("submit", (e) => submitRealMT5Account(e));
  document.getElementById("realCryptoForm")?.addEventListener("submit", (e) => submitRealCryptoAccount(e));

  // Form New Account Submit
  document.getElementById("newAccountForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("newAccName").value;
    const type = document.getElementById("newAccType").value;
    const balance = parseFloat(document.getElementById("newAccBalance").value);
    const leverage = parseInt(document.getElementById("newAccLeverage").value);

    try {
      const res = await fetch("/api/accounts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, type, initial_balance: balance, leverage })
      });
      const data = await res.json();
      if (data.success) {
        closeAccountModal();
        await fetchFullState();
        window.soundFx?.playAlert();
      }
    } catch (err) {
      alert("Gagal membuat akun");
    }
  });

  // Form Modify SL/TP Submit
  document.getElementById("modifyOrderForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const posId = document.getElementById("modifyPosId").value;
    const sl = parseFloat(document.getElementById("modifySL").value);
    const tp = parseFloat(document.getElementById("modifyTP").value);

    try {
      const res = await fetch("/api/order/modify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_id: posId, sl, tp })
      });
      const data = await res.json();
      if (data.success) {
        closeModifyModal();
        window.soundFx?.playClick();
      }
    } catch (err) {
      alert("Gagal mengubah SL/TP");
    }
  });
}

function selectSymbol(sym) {
  if (sym === appState.activeSymbol) return;
  window.soundFx?.playClick();
  loadSymbolData(sym, appState.activeTimeframe);
  renderTickerStrip();
}

async function executeQuickTrade(direction) {
  const lotInput = document.getElementById("quickLotInput");
  const lot = parseFloat(lotInput?.value || "0.1");

  try {
    const res = await fetch("/api/order/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: appState.activeSymbol,
        direction: direction,
        lot: lot,
        strategy: "Manual Trade"
      })
    });
    const data = await res.json();
    if (data.success) {
      if (direction === "BUY") window.soundFx?.playBuy();
      else window.soundFx?.playSell();
    } else {
      alert(data.error || "Gagal membuka order");
    }
  } catch (e) {
    alert("Koneksi gagal saat order");
  }
}

async function closeOrder(posId) {
  try {
    const res = await fetch("/api/order/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position_id: posId })
    });
    const data = await res.json();
    if (data.success) {
      window.soundFx?.playAlert();
    }
  } catch (e) {
    console.error(e);
  }
}

async function updateAISetting(partial) {
  try {
    const res = await fetch("/api/ai/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(partial)
    });
    const data = await res.json();
    if (data.success) {
      appState.aiSettings = data.settings;
    }
  } catch (e) {
    console.error(e);
  }
}

// 5. Modals Management
function openAccountModal() {
  const modal = document.getElementById("accountModal");
  if (!modal) return;

  const canDelete = appState.allAccounts.length > 1;
  const listContainer = document.getElementById("modalAccountList");
  listContainer.innerHTML = appState.allAccounts.map(acc => {
    const isActive = acc.is_active;
    const safeName = (acc.name || "Akun").replace(/'/g, "\\'");
    return `
      <div class="account-item-row ${isActive ? 'active' : ''}">
        <div class="acc-info-block">
          <div class="acc-name-text">
            ${acc.name} 
            <span class="acc-type-tag ${acc.type}">${acc.type.toUpperCase()}</span>
            ${isActive ? '<span style="color:#00f090; font-size:0.75rem; margin-left:6px;">● AKTIF</span>' : ''}
          </div>
          <div class="acc-details-text">
            Saldo: $${acc.balance.toLocaleString()} | Leverage: 1:${acc.leverage} | Broker: ${acc.credentials?.broker || 'Paper Engine'}
          </div>
        </div>
        <div class="acc-actions-wrap">
          ${!isActive ? `<button class="btn-switch-acc" onclick="window.switchAccount('${acc.id}')">Pilih Akun</button>` : ''}
          <button class="btn-reset-acc" onclick="window.resetAccountBalance('${acc.id}')">Reset Saldo</button>
          ${canDelete ? `<button class="btn-delete-acc" onclick="window.deleteAccount('${acc.id}', '${safeName}', ${isActive})" title="Hapus akun ${acc.name}">
            <span style="font-size:0.8rem; line-height:1;">🗑️</span>
            <span>Hapus</span>
          </button>` : ''}
        </div>
      </div>
    `;
  }).join("");

  modal.classList.add("open");
}

function closeAccountModal() {
  document.getElementById("accountModal")?.classList.remove("open");
}

async function switchAccount(accId) {
  try {
    const res = await fetch("/api/accounts/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accId })
    });
    const data = await res.json();
    if (data.success) {
      closeAccountModal();
      await fetchFullState();
      window.soundFx?.playClick();
    }
  } catch (e) {
    alert("Gagal beralih akun");
  }
}

async function resetAccountBalance(accId) {
  if (confirm("Reset saldo akun ini kembali ke saldo awal?")) {
    try {
      const res = await fetch("/api/accounts/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: accId })
      });
      const data = await res.json();
      if (data.success) {
        openAccountModal();
        await fetchFullState();
        window.soundFx?.playAlert();
      }
    } catch (e) {
      alert("Gagal reset saldo");
    }
  }
}

async function deleteAccount(accId, accName, isActive) {
  if (appState.allAccounts.length <= 1) {
    alert("Tidak dapat menghapus akun terakhir. Sistem membutuhkan minimal 1 akun aktif.");
    return;
  }

  const promptMsg = isActive 
    ? `⚠️ Perhatian: Akun "${accName}" saat ini sedang AKTIF.\n\nJika dihapus, posisi aktif akun ini akan dibersihkan dan akun lain akan otomatis dijadikan akun aktif.\n\nApakah Anda yakin ingin menghapus akun ini?`
    : `Apakah Anda yakin ingin menghapus akun "${accName}"?`;

  if (!confirm(promptMsg)) {
    return;
  }

  try {
    const res = await fetch(`/api/accounts/${accId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (res.ok && data.success) {
      await fetchFullState();
      openAccountModal();
      window.soundFx?.playAlert();
    } else {
      alert(data.detail || data.error || "Gagal menghapus akun");
    }
  } catch (e) {
    alert("Terjadi kesalahan jaringan saat menghapus akun");
  }
}

window.openAccountModal = openAccountModal;
window.closeAccountModal = closeAccountModal;
window.switchAccount = switchAccount;
window.resetAccountBalance = resetAccountBalance;
window.deleteAccount = deleteAccount;

function openModifyModal(posId, sl, tp, sym) {
  document.getElementById("modifyPosId").value = posId;
  document.getElementById("modifyPosSym").innerText = sym;
  document.getElementById("modifySL").value = sl || "";
  document.getElementById("modifyTP").value = tp || "";
  document.getElementById("modifyModal").classList.add("open");
}

function closeModifyModal() {
  document.getElementById("modifyModal")?.classList.remove("open");
}

// 6. AI API & URL Configuration Modal Handlers
function openAIConfigModal() {
  const modal = document.getElementById("aiConfigModal");
  if (!modal) return;

  const cfg = appState.aiApiConfig?.config || {};
  const presets = appState.aiApiConfig?.presets || {};

  const provSelect = document.getElementById("cfgAIProvider");
  const urlInput = document.getElementById("cfgAIUrl");
  const keyInput = document.getElementById("cfgAIApiKey");
  const modelInput = document.getElementById("cfgAIModel");
  const enabledChk = document.getElementById("cfgAIEnabled");
  const resultBox = document.getElementById("aiTestResultBox");

  if (provSelect) provSelect.value = cfg.provider || "openai";
  if (urlInput) urlInput.value = cfg.api_url || "https://api.openai.com/v1";
  if (keyInput) keyInput.value = cfg.api_key || "";
  if (modelInput) modelInput.value = cfg.model || "gpt-4o-mini";
  if (enabledChk) enabledChk.checked = !!cfg.enabled;
  if (resultBox) resultBox.style.display = "none";

  applyAIProviderPreset(provSelect.value, false);

  modal.classList.add("open");
}

function closeAIConfigModal() {
  document.getElementById("aiConfigModal")?.classList.remove("open");
}

function toggleApiKeyVisibility() {
  const keyInput = document.getElementById("cfgAIApiKey");
  const btn = document.getElementById("btnToggleApiKeyVis");
  if (!keyInput || !btn) return;

  if (keyInput.type === "password") {
    keyInput.type = "text";
    btn.innerText = "Sembunyikan";
  } else {
    keyInput.type = "password";
    btn.innerText = "Tampilkan";
  }
}

function applyAIProviderPreset(providerKey, overwrite = true) {
  const presets = appState.aiApiConfig?.presets || {
    openai: { default_url: "https://api.openai.com/v1", default_model: "gpt-4o-mini", doc: "Dapatkan API Key di platform.openai.com" },
    gemini: { default_url: "https://generativelanguage.googleapis.com/v1beta", default_model: "gemini-1.5-flash", doc: "Dapatkan API Key di aistudio.google.com" },
    deepseek: { default_url: "https://api.deepseek.com/v1", default_model: "deepseek-chat", doc: "Dapatkan API Key di platform.deepseek.com" },
    groq: { default_url: "https://api.groq.com/openai/v1", default_model: "llama-3.3-70b-versatile", doc: "Dapatkan API Key di console.groq.com" },
    ollama: { default_url: "http://localhost:11434/v1", default_model: "llama3:latest", doc: "Ollama berjalan di komputer lokal (tanpa perlu API key)" },
    custom: { default_url: "https://your-custom-ai-host.com/v1", default_model: "default", doc: "Endpoint API kustom yang kompatibel dengan format OpenAI" }
  };

  const p = presets[providerKey];
  if (!p) return;

  const urlInput = document.getElementById("cfgAIUrl");
  const modelInput = document.getElementById("cfgAIModel");
  const docLink = document.getElementById("cfgAIDocLink");
  const urlHint = document.getElementById("cfgAIUrlHint");

  if (overwrite) {
    if (urlInput) urlInput.value = p.default_url;
    if (modelInput) modelInput.value = p.default_model;
  }
  if (docLink) docLink.innerText = p.doc;
  if (urlHint) urlHint.innerText = `Default URL: ${p.default_url}`;
}

async function testAIConnectionAction() {
  const provider = document.getElementById("cfgAIProvider").value;
  const apiUrl = document.getElementById("cfgAIUrl").value.trim();
  const apiKey = document.getElementById("cfgAIApiKey").value.trim();
  const model = document.getElementById("cfgAIModel").value.trim();
  const resultBox = document.getElementById("aiTestResultBox");
  const btn = document.getElementById("btnTestAIConnection");

  if (!apiUrl || !model) {
    alert("Mohon isi URL Endpoint dan Model ID terlebih dahulu");
    return;
  }

  btn.disabled = true;
  btn.innerText = "⏳ Menguji Koneksi...";
  resultBox.style.display = "block";
  resultBox.style.background = "rgba(0, 242, 254, 0.08)";
  resultBox.style.border = "1px solid rgba(0, 242, 254, 0.3)";
  resultBox.style.color = "var(--neon-cyan)";
  resultBox.innerText = `Menghubungi ${apiUrl} (Model: ${model})...`;

  try {
    const res = await fetch("/api/ai/test-connection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: provider,
        api_url: apiUrl,
        api_key: apiKey,
        model: model
      })
    });
    const data = await res.json();

    if (data.success) {
      resultBox.style.background = "rgba(0, 240, 144, 0.12)";
      resultBox.style.border = "1px solid rgba(0, 240, 144, 0.4)";
      resultBox.style.color = "var(--neon-green)";
      resultBox.innerHTML = `
        ✓ <b>Koneksi Sukses! (${data.latency_ms} ms)</b><br>
        Balasan Model: <i>"${data.reply}"</i>
      `;
      window.soundFx?.playAlert();
    } else {
      resultBox.style.background = "rgba(255, 51, 102, 0.12)";
      resultBox.style.border = "1px solid rgba(255, 51, 102, 0.4)";
      resultBox.style.color = "var(--neon-red)";
      resultBox.innerHTML = `
        ✗ <b>Gagal Terhubung:</b><br>
        ${data.error || 'Respons tidak valid dari server API'}
      `;
    }
  } catch (err) {
    resultBox.style.background = "rgba(255, 51, 102, 0.12)";
    resultBox.style.border = "1px solid rgba(255, 51, 102, 0.4)";
    resultBox.style.color = "var(--neon-red)";
    resultBox.innerText = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerText = "⚡ Uji Koneksi API";
  }
}

async function saveAIConfigAction(e) {
  e.preventDefault();
  const provider = document.getElementById("cfgAIProvider").value;
  const apiUrl = document.getElementById("cfgAIUrl").value.trim();
  const apiKey = document.getElementById("cfgAIApiKey").value.trim();
  const model = document.getElementById("cfgAIModel").value.trim();
  const enabled = document.getElementById("cfgAIEnabled").checked;

  try {
    const res = await fetch("/api/ai/api-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        api_url: apiUrl,
        api_key: apiKey,
        model,
        enabled
      })
    });
    const data = await res.json();
    if (data.success) {
      appState.aiApiConfig.config = data.config;
      renderAIBrainBadge();
      closeAIConfigModal();
      window.soundFx?.playAlert();
    } else {
      alert("Gagal menyimpan konfigurasi AI");
    }
  } catch (err) {
    alert("Error saat menyimpan konfigurasi: " + err.message);
  }
}

// 7. Real Broker Account Handlers
function openConnectRealModal() {
  const modal = document.getElementById("connectRealModal");
  if (!modal) return;
  modal.classList.add("open");
}

function closeConnectRealModal() {
  document.getElementById("connectRealModal")?.classList.remove("open");
}

function selectRealPlatform(platform) {
  const btnMT5 = document.getElementById("tabRealPlatformMT5");
  const btnCrypto = document.getElementById("tabRealPlatformCrypto");
  const formMT5 = document.getElementById("realMT5Form");
  const formCrypto = document.getElementById("realCryptoForm");

  if (platform === "mt5") {
    btnMT5.classList.add("active");
    btnCrypto.classList.remove("active");
    formMT5.style.display = "flex";
    formCrypto.style.display = "none";
  } else {
    btnCrypto.classList.add("active");
    btnMT5.classList.remove("active");
    formCrypto.style.display = "flex";
    formMT5.style.display = "none";
  }
  window.soundFx?.playClick();
}

function onBrokerPresetChange(broker) {
  const serverInput = document.getElementById("realMT5Server");
  if (!serverInput) return;

  const presets = {
    "Exness": "Exness-MT5Trial7",
    "IC Markets": "ICMarketsSC-Live01",
    "XM Global": "XMGlobal-MT5",
    "OctaFX": "OctaFX-Real",
    "FBS": "FBS-Real",
    "MetaQuotes": "MetaQuotes-Demo",
    "Custom": ""
  };
  serverInput.value = presets[broker] || "";
}

async function autoSyncActiveMT5Terminal() {
  const btn = document.getElementById("btnAutoSyncMT5");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span>⏳ Menghubungkan ke Terminal MT5 Exness...</span>`;
  }

  try {
    const res = await fetch("/api/mt5/auto-sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await res.json();
    if (res.ok && data.success) {
      window.soundFx?.playAlert();
      const curr = data.metrics.currency || "USD";
      const formattedBal = formatCurrency(data.metrics.balance, curr);
      alert(`🎉 SINKRONISASI BERHASIL!\n\n` +
            `Akun: ${data.account.name}\n` +
            `Broker: ${data.metrics.company}\n` +
            `Server: ${data.metrics.server}\n` +
            `Login ID: ${data.metrics.login}\n` +
            `Saldo Riil: ${formattedBal}\n` +
            `Leverage: 1:${data.metrics.leverage}\n\n` +
            `Akun Anda sekarang aktif dan terhubung langsung dengan terminal Exness!`);
      closeConnectRealModal();
      await fetchFullState();
    } else {
      window.soundFx?.playError();
      alert("Gagal Sinkronisasi Terminal MT5:\n\n" + (data.detail || data.error || "Terminal MetaTrader 5 belum aktif atau belum login."));
    }
  } catch (err) {
    window.soundFx?.playError();
    alert("Koneksi gagal: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

function togglePasswordVisibility(inputId, btnId) {
  const input = document.getElementById(inputId);
  const btn = document.getElementById(btnId);
  if (!input || !btn) return;

  if (input.type === "password") {
    input.type = "text";
    btn.innerText = "Tutup";
  } else {
    input.type = "password";
    btn.innerText = "Lihat";
  }
}

async function submitRealMT5Account(e) {
  e.preventDefault();
  const name = document.getElementById("realMT5Name").value.trim();
  const broker = document.getElementById("realMT5Broker").value;
  const server = document.getElementById("realMT5Server").value.trim();
  const login = document.getElementById("realMT5Login").value.trim();
  const password = document.getElementById("realMT5Password").value;
  const balance = parseFloat(document.getElementById("realMT5Balance").value || "1000");
  const leverage = parseInt(document.getElementById("realMT5Leverage").value || "100");

  try {
    const res = await fetch("/api/auth/connect-real", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "mt5",
        account_name: name,
        broker: broker,
        server: server,
        login: login,
        password: password,
        initial_balance: balance,
        leverage: leverage,
        currency: "USD"
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      closeConnectRealModal();
      await fetchFullState();
      window.soundFx?.playAlert();
      alert(`Selamat! Akun Real MetaTrader 5 [${name}] berhasil terhubung dan diaktifkan.`);
    } else {
      window.soundFx?.playError();
      alert("Gagal menghubungkan akun MT5:\n\n" + (data.detail || data.error || "Data tidak valid atau login ditolak broker."));
    }
  } catch (err) {
    window.soundFx?.playError();
    alert("Koneksi gagal: " + err.message);
  }
}


async function submitRealCryptoAccount(e) {
  e.preventDefault();
  const name = document.getElementById("realCryptoName").value.trim();
  const exchange = document.getElementById("realCryptoExchange").value;
  const marketType = document.getElementById("realCryptoMarketType").value;
  const apiKey = document.getElementById("realCryptoApiKey").value.trim();
  const apiSecret = document.getElementById("realCryptoApiSecret").value.trim();
  const balance = parseFloat(document.getElementById("realCryptoBalance").value || "500");
  const leverage = parseInt(document.getElementById("realCryptoLeverage").value || "10");

  try {
    const res = await fetch("/api/auth/connect-real", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: "crypto",
        account_name: name,
        exchange: exchange,
        market_type: marketType,
        api_key: apiKey,
        api_secret: apiSecret,
        initial_balance: balance,
        leverage: leverage,
        currency: "USDT"
      })
    });
    const data = await res.json();
    if (data.success) {
      closeConnectRealModal();
      await fetchFullState();
      window.soundFx?.playAlert();
      alert(`Selamat! Akun Real Crypto [${name}] (${exchange}) berhasil terhubung dan diaktifkan.`);
    } else {
      alert("Gagal menghubungkan akun Crypto: " + (data.error || "Data tidak valid"));
    }
  } catch (err) {
    alert("Koneksi gagal: " + err.message);
  }
}

// --------------------------------------------------------------------------
// 7. BACKTEST LABORATORIUM RENDERING & CHARTING
// --------------------------------------------------------------------------
let backtestEquityData = [];

function renderBacktestResults(res) {
  const m = res.metrics;
  if (!m) return;

  const winRateEl = document.getElementById("btWinRate");
  const pnlEl = document.getElementById("btNetProfit");
  const pfEl = document.getElementById("btProfitFactor");
  const ddEl = document.getElementById("btMaxDrawdown");
  const tradesEl = document.getElementById("btTotalTrades");
  const summaryEl = document.getElementById("btResultSummary");

  if (winRateEl) {
    winRateEl.innerText = `${m.win_rate_pct}%`;
    winRateEl.className = `bt-stat-val ${m.win_rate_pct >= 50 ? 'up' : 'down'}`;
  }
  if (pnlEl) {
    const sign = m.net_profit >= 0 ? "+" : "";
    pnlEl.innerText = `${sign}$${m.net_profit.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})} (${m.net_profit_pct}%)`;
    pnlEl.className = `bt-stat-val ${m.net_profit >= 0 ? 'up' : 'down'}`;
  }
  if (pfEl) {
    pfEl.innerText = m.profit_factor;
    pfEl.className = `bt-stat-val ${m.profit_factor >= 1.5 ? 'up' : ''}`;
  }
  if (ddEl) {
    ddEl.innerText = `-${m.max_drawdown_pct}%`;
  }
  if (tradesEl) {
    tradesEl.innerText = `${m.total_trades} (${m.winning_trades}W / ${m.losing_trades}L)`;
  }
  if (summaryEl) {
    summaryEl.innerText = `Simulasi ${res.candles_analyzed} Bar Candles (${res.symbol}) • Return: ${m.net_profit_pct}%`;
  }

  // Populate Trade Table
  const tbody = document.getElementById("backtestTableBody");
  if (tbody) {
    if (!res.trades || res.trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:16px;">Tidak ada transaksi terpicu dengan threshold confidence ini. Coba turunkan threshold minimum.</td></tr>';
    } else {
      tbody.innerHTML = res.trades.slice().reverse().map(t => {
        const isWin = t.pnl >= 0;
        const colorClass = isWin ? "up" : "down";
        const sign = isWin ? "+" : "";
        return `<tr>
          <td>#${t.trade_num}</td>
          <td><span class="order-badge ${t.type.toLowerCase()}">${t.type}</span></td>
          <td style="font-family:var(--font-mono); font-size:0.75rem;">${t.entry_time || "-"}</td>
          <td style="font-family:var(--font-mono);">${t.entry_price}</td>
          <td style="font-family:var(--font-mono);">${t.exit_price}</td>
          <td class="${colorClass}" style="font-family:var(--font-mono); font-weight:700;">${sign}$${t.pnl.toFixed(2)}</td>
          <td class="${colorClass}" style="font-family:var(--font-mono); font-weight:700;">${sign}${t.pnl_pct.toFixed(2)}%</td>
          <td><span style="font-size:0.75rem; color:var(--text-muted);">${t.reason}</span></td>
        </tr>`;
      }).join("");
    }
  }

  // Draw Equity Curve
  backtestEquityData = res.equity_curve || [];
  drawBacktestEquityChart(backtestEquityData);
}

function drawBacktestEquityChart(curve) {
  const canvas = document.getElementById("backtestEquityChart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = rect.width > 0 ? rect.width : 600;
  const height = rect.height > 0 ? rect.height : 170;

  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, width, height);

  if (!curve || curve.length < 2) {
    ctx.fillStyle = "#64748b";
    ctx.font = "12px monospace";
    ctx.textAlign = "center";
    ctx.fillText("Data simulasi belum tersedia", width / 2, height / 2);
    return;
  }

  const balances = curve.map(c => c.balance);
  let minBal = Math.min(...balances);
  let maxBal = Math.max(...balances);
  if (minBal === maxBal) {
    minBal *= 0.99;
    maxBal *= 1.01;
  } else {
    minBal *= 0.998;
    maxBal *= 1.002;
  }
  const range = maxBal - minBal || 1;

  const padLeft = 60;
  const padRight = 15;
  const padTop = 15;
  const padBottom = 25;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  // Grid lines & Y Axis Labels
  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = padTop + (chartH / 3) * i;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();

    const priceVal = maxBal - (range / 3) * i;
    ctx.fillStyle = "#64748b";
    ctx.font = "10px monospace";
    ctx.textAlign = "right";
    ctx.fillText("$" + Math.round(priceVal).toLocaleString(), padLeft - 6, y + 3);
  }

  // Draw Line
  ctx.beginPath();
  curve.forEach((pt, idx) => {
    const x = padLeft + (idx / (curve.length - 1)) * chartW;
    const y = padTop + chartH - ((pt.balance - minBal) / range) * chartH;
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });

  const isProfitable = balances[balances.length - 1] >= balances[0];
  const strokeColor = isProfitable ? "#00f090" : "#ff3366";
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 2.5;
  ctx.shadowColor = strokeColor;
  ctx.shadowBlur = 8;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Fill Gradient Under Curve
  ctx.lineTo(padLeft + chartW, padTop + chartH);
  ctx.lineTo(padLeft, padTop + chartH);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, padTop, 0, padTop + chartH);
  grad.addColorStop(0, isProfitable ? "rgba(0, 240, 144, 0.25)" : "rgba(255, 51, 102, 0.25)");
  grad.addColorStop(1, "rgba(0, 0, 0, 0)");
  ctx.fillStyle = grad;
  ctx.fill();

  // Point at the end
  const lastX = padLeft + chartW;
  const lastY = padTop + chartH - ((balances[balances.length - 1] - minBal) / range) * chartH;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
  ctx.fillStyle = strokeColor;
  ctx.fill();
}

