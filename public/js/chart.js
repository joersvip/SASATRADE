// High-performance Canvas Candlestick & Volume Chart Engine
class TradingChartEngine {
  constructor(canvasId, tooltipId = null) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.tooltipId = tooltipId;
    
    this.candles = [];
    this.markers = []; // AI buy/sell markers
    this.symbol = "EURUSD";
    this.digits = 5;
    
    // Viewport & Scaling
    this.candleWidth = 8;
    this.candleGap = 4;
    this.offsetX = 0; // panning offset
    this.isDragging = false;
    this.dragStartX = 0;
    this.mouseX = -1;
    this.mouseY = -1;

    // Theme Colors
    this.colors = {
      bg: "#090d16",
      grid: "rgba(255, 255, 255, 0.04)",
      text: "#64748b",
      bull: "#00f090",
      bear: "#ff3366",
      ema9: "#00f2fe",
      ema21: "#ffb703",
      sma50: "#8a2be2",
      crosshair: "rgba(255, 255, 255, 0.25)",
      volumeBull: "rgba(0, 240, 144, 0.2)",
      volumeBear: "rgba(255, 51, 102, 0.2)"
    };

    this._setupEvents();
    this.resize();
  }

  _setupEvents() {
    window.addEventListener('resize', () => this.resize());

    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.dragStartX = e.clientX - this.offsetX;
    });

    window.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.mouseX = e.clientX - rect.left;
      this.mouseY = e.clientY - rect.top;

      if (this.isDragging) {
        this.offsetX = e.clientX - this.dragStartX;
        this.render();
      } else if (this.mouseX >= 0 && this.mouseX <= rect.width && this.mouseY >= 0 && this.mouseY <= rect.height) {
        this.render();
      }
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.mouseX = -1;
      this.mouseY = -1;
      this.render();
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      const newWidth = Math.max(3, Math.min(30, this.candleWidth * zoomFactor));
      this.candleWidth = newWidth;
      this.candleGap = Math.max(1, Math.round(newWidth * 0.4));
      this.render();
    });
  }

  resize() {
    if (!this.canvas || !this.canvas.parentElement) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;

    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.scale(dpr, dpr);

    if (this.candles && this.candles.length > 0) {
      const totalW = this.candles.length * (this.candleWidth + this.candleGap);
      const rightMargin = 80;
      this.offsetX = (this.width - rightMargin) - totalW;
    }
    this.render();
  }

  setData(candles, symbol, digits = 5, markers = []) {
    this.candles = candles || [];
    this.symbol = symbol || this.symbol;
    this.digits = digits;
    this.markers = markers || [];
    this.calculateIndicators();
    // Default scroll to rightmost latest candle
    const totalW = this.candles.length * (this.candleWidth + this.candleGap);
    const rightMargin = 80;
    this.offsetX = (this.width - rightMargin) - totalW;
    if (this.width > 0 && this.height > 0) {
      this.render();
    }
  }

  updateLivePrice(price, volume = 0) {
    if (!this.candles || this.candles.length === 0 || !price) return;
    this.livePrice = price;
    const last = this.candles[this.candles.length - 1];
    last.close = price;
    if (price > last.high) last.high = price;
    if (price < last.low) last.low = price;
    if (volume > 0) last.volume += volume;

    this.calculateIndicators();
    this.render();
  }

  calculateIndicators() {
    if (!this.candles || this.candles.length === 0) return;
    const closes = this.candles.map(c => c.close);
    
    // EMA 9 & 21
    const calcEMA = (period) => {
      const k = 2 / (period + 1);
      const res = [];
      let ema = closes[0];
      for (let i = 0; i < closes.length; i++) {
        if (i < period) {
          ema = (ema * i + closes[i]) / (i + 1);
        } else {
          ema = (closes[i] * k) + (ema * (1 - k));
        }
        res.push(ema);
      }
      return res;
    };

    // SMA 50
    const calcSMA = (period) => {
      const res = [];
      for (let i = 0; i < closes.length; i++) {
        if (i < period - 1) {
          res.push(null);
        } else {
          const slice = closes.slice(i - period + 1, i + 1);
          res.push(slice.reduce((a, b) => a + b, 0) / period);
        }
      }
      return res;
    };

    const ema9 = calcEMA(9);
    const ema21 = calcEMA(21);
    const sma50 = calcSMA(min(50, this.candles.length));

    for (let i = 0; i < this.candles.length; i++) {
      this.candles[i].ema9 = ema9[i];
      this.candles[i].ema21 = ema21[i];
      this.candles[i].sma50 = sma50[i];
    }
  }

  render() {
    if (!this.ctx || !this.width || !this.height) return;
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const priceScaleW = 75;
    const timeScaleH = 26;
    const chartAreaW = w - priceScaleW;
    const chartAreaH = h - timeScaleH;
    const volumeH = chartAreaH * 0.18;

    // Clear background
    ctx.fillStyle = this.colors.bg;
    ctx.fillRect(0, 0, w, h);

    if (!this.candles || this.candles.length === 0) {
      ctx.fillStyle = this.colors.text;
      ctx.font = "14px 'Outfit', sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Memuat data candlestick...", w / 2, h / 2);
      return;
    }

    const step = this.candleWidth + this.candleGap;
    // Visible index range
    const startIdx = Math.max(0, Math.floor((-this.offsetX) / step));
    const endIdx = Math.min(this.candles.length - 1, Math.ceil((chartAreaW - this.offsetX) / step));

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVol = 0;

    for (let i = startIdx; i <= endIdx; i++) {
      const c = this.candles[i];
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (c.volume > maxVol) maxVol = c.volume;
    }

    if (minPrice === Infinity || maxPrice === -Infinity) {
      minPrice = this.candles[0].low;
      maxPrice = this.candles[0].high;
    }

    // Add padding to price range
    const priceRange = Math.max(maxPrice - minPrice, 0.0001);
    const priceMargin = priceRange * 0.08;
    const renderMin = minPrice - priceMargin;
    const renderMax = maxPrice + priceMargin;
    const totalRange = renderMax - renderMin;

    const getY = (p) => chartAreaH - ((p - renderMin) / totalRange) * (chartAreaH - volumeH) - volumeH;

    // 1. Draw Grid Lines & Price Labels
    ctx.strokeStyle = this.colors.grid;
    ctx.lineWidth = 1;
    ctx.font = "10px 'JetBrains Mono', monospace";
    ctx.fillStyle = this.colors.text;
    ctx.textAlign = "left";

    const gridRows = 6;
    for (let r = 0; r <= gridRows; r++) {
      const y = (chartAreaH / gridRows) * r;
      const priceVal = renderMax - (r / gridRows) * totalRange;

      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartAreaW, y);
      ctx.stroke();

      ctx.fillText(priceVal.toFixed(this.digits), chartAreaW + 8, y + 4);
    }

    // 2. Draw Indicator Lines (EMA 9, EMA 21, SMA 50)
    const drawLine = (prop, color, dash = []) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash(dash);
      ctx.beginPath();
      let started = false;

      for (let i = startIdx; i <= endIdx; i++) {
        const val = this.candles[i][prop];
        if (val === null || val === undefined) continue;
        const x = this.offsetX + (i * step) + (this.candleWidth / 2);
        const y = getY(val);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.setLineDash([]);
    };

    drawLine("sma50", this.colors.sma50);
    drawLine("ema21", this.colors.ema21);
    drawLine("ema9", this.colors.ema9);

    // 3. Draw Candlesticks & Volume
    let hoveredCandle = null;
    let hoveredX = 0;

    for (let i = startIdx; i <= endIdx; i++) {
      const c = this.candles[i];
      const x = this.offsetX + (i * step);
      const isBull = c.close >= c.open;
      const color = isBull ? this.colors.bull : this.colors.bear;

      // Volume bar
      const vRatio = maxVol > 0 ? c.volume / maxVol : 0;
      const vBarH = vRatio * (volumeH * 0.9);
      ctx.fillStyle = isBull ? this.colors.volumeBull : this.colors.volumeBear;
      ctx.fillRect(x, chartAreaH - vBarH, this.candleWidth, vBarH);

      // Wick
      const highY = getY(c.high);
      const lowY = getY(c.low);
      const openY = getY(c.open);
      const closeY = getY(c.close);

      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x + this.candleWidth / 2, highY);
      ctx.lineTo(x + this.candleWidth / 2, lowY);
      ctx.stroke();

      // Body
      const topY = Math.min(openY, closeY);
      const bodyH = Math.max(Math.abs(openY - closeY), 1.5);

      ctx.fillStyle = color;
      ctx.fillRect(x, topY, this.candleWidth, bodyH);

      // Check hover
      if (this.mouseX >= x && this.mouseX <= x + step) {
        hoveredCandle = c;
        hoveredX = x + this.candleWidth / 2;
      }
    }

    // 3b. Real-time Live Price Dotted Line & Axis Badge
    const curPrice = this.livePrice || (this.candles.length > 0 ? this.candles[this.candles.length - 1].close : null);
    if (curPrice !== null) {
      const curY = getY(curPrice);
      if (curY >= 0 && curY <= chartAreaH) {
        const lastCandle = this.candles[this.candles.length - 1];
        const isUp = lastCandle && lastCandle.close >= lastCandle.open;
        const lineColor = isUp ? "#00f090" : "#ff3366";

        ctx.strokeStyle = lineColor;
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(0, curY);
        ctx.lineTo(chartAreaW, curY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Live badge on right price scale
        ctx.fillStyle = lineColor;
        ctx.fillRect(chartAreaW, curY - 9, priceScaleW, 18);
        ctx.fillStyle = "#030712";
        ctx.font = "bold 10px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        ctx.fillText(curPrice.toFixed(this.digits), chartAreaW + 6, curY + 4);
      }
    }

    // 4. Draw AI Order Markers
    if (this.markers && this.markers.length > 0) {
      for (const m of this.markers) {
        if (m.symbol !== this.symbol) continue;
        const my = getY(m.price);
        const mx = chartAreaW - 40; // Pin to recent price action

        ctx.fillStyle = m.direction === "BUY" ? "#00f090" : "#ff3366";
        ctx.beginPath();
        if (m.direction === "BUY") {
          ctx.moveTo(mx, my + 14);
          ctx.lineTo(mx - 7, my + 26);
          ctx.lineTo(mx + 7, my + 26);
        } else {
          ctx.moveTo(mx, my - 14);
          ctx.lineTo(mx - 7, my - 26);
          ctx.lineTo(mx + 7, my - 26);
        }
        ctx.closePath();
        ctx.fill();

        ctx.font = "bold 9px 'Outfit', sans-serif";
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.fillText(m.direction, mx, m.direction === "BUY" ? my + 38 : my - 30);
      }
    }

    // 5. Crosshair & Tooltip Overlay
    if (this.mouseX >= 0 && this.mouseX <= chartAreaW && this.mouseY >= 0 && this.mouseY <= chartAreaH) {
      ctx.strokeStyle = this.colors.crosshair;
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(hoveredX || this.mouseX, 0);
      ctx.lineTo(hoveredX || this.mouseX, chartAreaH);
      ctx.stroke();

      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(0, this.mouseY);
      ctx.lineTo(chartAreaW, this.mouseY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Floating price badge on scale
      const hoverPrice = renderMax - (this.mouseY / chartAreaH) * totalRange;
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(chartAreaW, this.mouseY - 10, priceScaleW, 20);
      ctx.fillStyle = "#00f2fe";
      ctx.font = "bold 10px 'JetBrains Mono', monospace";
      ctx.textAlign = "left";
      ctx.fillText(hoverPrice.toFixed(this.digits), chartAreaW + 6, this.mouseY + 4);

      // Update Tooltip DOM element if available
      if (hoveredCandle) {
        this.updateTooltipDOM(hoveredCandle);
      }
    }

    // 6. Time Scale labels on bottom
    ctx.fillStyle = this.colors.text;
    ctx.font = "9px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";

    const timeSteps = 5;
    for (let t = 0; t <= timeSteps; t++) {
      const idx = Math.floor(startIdx + (t / timeSteps) * (endIdx - startIdx));
      if (this.candles[idx]) {
        const x = this.offsetX + (idx * step) + (this.candleWidth / 2);
        if (x >= 0 && x <= chartAreaW) {
          const date = new Date(this.candles[idx].time * 1000);
          const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          ctx.fillText(timeStr, x, h - 8);
        }
      }
    }
  }

  updateTooltipDOM(c) {
    const el = document.getElementById(this.tooltipId || "chartTooltip");
    if (!el) return;
    const isBull = c.close >= c.open;
    const date = new Date(c.time * 1000).toLocaleTimeString();

    el.innerHTML = `
      <span>TIME: <b style="color:#94a3b8">${date}</b></span>
      <span>O: <b style="color:#f8fafc">${c.open.toFixed(this.digits)}</b></span>
      <span>H: <b style="color:#00f090">${c.high.toFixed(this.digits)}</b></span>
      <span>L: <b style="color:#ff3366">${c.low.toFixed(this.digits)}</b></span>
      <span>C: <b style="color:${isBull ? '#00f090' : '#ff3366'}">${c.close.toFixed(this.digits)}</b></span>
      <span>VOL: <b style="color:#00f2fe">${c.volume.toFixed(0)}</b></span>
      <span style="color:#00f2fe">EMA9: ${c.ema9 ? c.ema9.toFixed(this.digits) : '-'}</span>
      <span style="color:#ffb703">EMA21: ${c.ema21 ? c.ema21.toFixed(this.digits) : '-'}</span>
    `;
  }
}

function min(a, b) {
  return a < b ? a : b;
}
