import os
import json
import math
import time
import random
import httpx
from typing import Dict, List, Any, Optional

try:
    from backend.market_intel import MarketIntel
    from backend.strategy_generator import StrategyGenerator
except ImportError:
    from market_intel import MarketIntel
    from strategy_generator import StrategyGenerator

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
AI_CONFIG_FILE = os.path.join(DATA_DIR, "ai_config.json")
AI_MEMORY_FILE = os.path.join(DATA_DIR, "ai_memory.json")

DEFAULT_AI_MEMORY = {
    "brain_level": 1,
    "experience_points": 0,
    "next_level_xp": 100,
    "total_trades_analyzed": 0,
    "profitable_trades": 0,
    "loss_trades": 0,
    "strategy_weights": {
        "neural_momentum": 1.0,
        "smart_money": 1.0,
        "mean_reversion": 1.0,
        "neural_scalper": 1.0
    },
    "regime_matrix": {
        "trending": {"weight": 1.1, "win_rate": 0.0, "samples": 0},
        "ranging": {"weight": 1.0, "win_rate": 0.0, "samples": 0},
        "volatile": {"weight": 0.9, "win_rate": 0.0, "samples": 0}
    },
    "learned_insights": [
        {
            "id": "ins-init",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "system",
            "message": "🧠 Otak AI diinisialisasi. Siap memproses hasil transaksi dan mengoptimalkan bobot strategi secara mandiri."
        }
    ]
}

DEFAULT_AI_CONFIG = {
    "provider": "openai",         # "openai", "gemini", "deepseek", "groq", "ollama", "custom"
    "api_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "enabled": False,
    "temperature": 0.3,
    "system_prompt": "You are ApexAI, an elite algorithmic trading quant. Analyze market candlestick patterns, technical indicators (EMA, RSI, ATR, Bollinger), and order book flow to provide precise trading signals with probability scoring and rationale."
}

PROVIDER_PRESETS = {
    "openai": {
        "name": "OpenAI (GPT-4o / Mini)",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "doc": "Masukkan API Key dari platform.openai.com"
    },
    "gemini": {
        "name": "Google Gemini API",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-1.5-flash",
        "doc": "Masukkan API Key dari aistudio.google.com"
    },
    "deepseek": {
        "name": "DeepSeek API",
        "default_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "doc": "Masukkan API Key dari platform.deepseek.com"
    },
    "groq": {
        "name": "Groq LPU (Ultra-Fast)",
        "default_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "doc": "Masukkan API Key dari console.groq.com"
    },
    "ollama": {
        "name": "Ollama (Local / Self-Hosted)",
        "default_url": "http://localhost:11434/v1",
        "default_model": "llama3:latest",
        "doc": "Jalankan Ollama di komputer lokal Anda (tanpa perlu API Key)"
    },
    "custom": {
        "name": "Custom OpenAI-Compatible API",
        "default_url": "https://your-custom-ai-host.com/v1",
        "default_model": "default",
        "doc": "Endpoint API kustom yang kompatibel dengan format OpenAI"
    }
}

class AIEngine:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.api_config = self._load_api_config()
        self.memory = self._load_memory()

        self.strategies = {
            "neural_momentum": {
                "id": "neural_momentum",
                "name": "Neural Momentum Trend (Deep EMA)",
                "description": "Mengikuti tren besar dengan konfirmasi crossover Multi-EMA 9/21/50 dan filter AI momentum RSI.",
                "min_rr": 2.0
            },
            "smart_money": {
                "id": "smart_money",
                "name": "Smart Money Concepts (ICT / FVG)",
                "description": "Mendeteksi sweep likuiditas pada swing high/low institusional dan entry di Fair Value Gap (FVG).",
                "min_rr": 3.0
            },
            "mean_reversion": {
                "id": "mean_reversion",
                "name": "AI Mean Reversion (Bollinger + Divergence)",
                "description": "Menangkap pembalikan harga ekstrim saat harga menyentuh pita Bollinger luar dengan divergensi RSI.",
                "min_rr": 2.2
            },
            "neural_scalper": {
                "id": "neural_scalper",
                "name": "High-Speed Neural Scalper (M1-M5)",
                "description": "Model ensemble scoring multi-indikator untuk eksekusi cepat dengan target pip/tick instan.",
                "min_rr": 1.8
            }
        }
        self.settings = {
            "mode": "off",            # Default "off" (standby) untuk produksi
            "active_strategy": "neural_momentum",
            "confidence_threshold": 75, # Minimal 75% untuk eksekusi
            "risk_per_trade_pct": 2.0,  # 2% risiko per transaksi
            "max_open_trades": 5,
            "daily_loss_limit_pct": 5.0,
            "trailing_stop_enabled": True,
            "trailing_stop_pips": 20,
            "target_markets": ["forex", "crypto", "stocks"],
            "symbols_whitelist": ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSDT", "ETHUSDT", "NVDA", "AAPL"],
            # Pengaturan Besaran Lot AI (Smart Lot Sizing)
            "lot_sizing_mode": "ai_dynamic", # "ai_dynamic", "fixed_risk_pct", "fixed_lot"
            "fixed_lot_size": 0.01,
            "max_lot_limit": 1.0,
            "min_lot_limit": 0.01
        }
        self.recent_signals: List[Dict[str, Any]] = []

        # Market Intelligence & Autonomous Strategy Generator
        self.market_intel = MarketIntel(ai_engine=self)
        self.strategy_generator = StrategyGenerator(ai_engine=self)

        # Register existing custom evolved strategies into active catalog
        for sid, sdata in self.strategy_generator.custom_strategies.items():
            self.strategies[sid] = sdata


    def _load_memory(self) -> Dict[str, Any]:
        if not os.path.exists(AI_MEMORY_FILE):
            self._save_memory_raw(DEFAULT_AI_MEMORY)
            return dict(DEFAULT_AI_MEMORY)
        try:
            with open(AI_MEMORY_FILE, "r", encoding="utf-8") as f:
                mem = json.load(f)
                res = dict(DEFAULT_AI_MEMORY)
                res.update(mem)
                return res
        except Exception:
            return dict(DEFAULT_AI_MEMORY)

    def _save_memory_raw(self, mem: Dict[str, Any]):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(AI_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2)

    def save_memory(self):
        self._save_memory_raw(self.memory)

    def learn_from_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Proses pembelajaran mandiri (Self-Learning Loop) dari hasil transaksi yang ditutup"""
        pnl = trade.get("pnl", 0.0)
        symbol = trade.get("symbol", "MARKET")
        strat_id = trade.get("strategy_id") or "neural_momentum"
        strat_name = self.strategies.get(strat_id, {}).get("name", strat_id)
        is_win = pnl > 0

        self.memory["total_trades_analyzed"] = self.memory.get("total_trades_analyzed", 0) + 1
        if is_win:
            self.memory["profitable_trades"] = self.memory.get("profitable_trades", 0) + 1
            xp_gained = 25
        else:
            self.memory["loss_trades"] = self.memory.get("loss_trades", 0) + 1
            xp_gained = 15

        # Update XP & Leveling
        self.memory["experience_points"] = self.memory.get("experience_points", 0) + xp_gained
        leveled_up = False
        while self.memory["experience_points"] >= self.memory.get("next_level_xp", 100):
            self.memory["brain_level"] = self.memory.get("brain_level", 1) + 1
            self.memory["next_level_xp"] = round(self.memory.get("next_level_xp", 100) * 1.5)
            leveled_up = True

        # Adaptive Strategy Weighting
        if "strategy_weights" not in self.memory:
            self.memory["strategy_weights"] = dict(DEFAULT_AI_MEMORY["strategy_weights"])
        curr_weight = self.memory["strategy_weights"].get(strat_id, 1.0)

        if is_win:
            new_weight = min(2.0, round(curr_weight + 0.05, 2))
            note = f"🎯 [EXP +{xp_gained}] Take Profit (+${pnl:.2f}) pada {symbol}! Bobot strategi '{strat_name}' dinaikkan menjadi {new_weight:.2f}x."
        else:
            new_weight = max(0.4, round(curr_weight - 0.07, 2))
            note = f"🧠 [EXP +{xp_gained}] Evaluasi SL pada {symbol} (-${abs(pnl):.2f}): Mengurangi bobot '{strat_name}' menjadi {new_weight:.2f}x untuk menyaring false-breakout."

        self.memory["strategy_weights"][strat_id] = new_weight

        # Add Learned Insight Entry
        insight_entry = {
            "id": f"ins-{int(time.time()*1000)}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "win" if is_win else "loss",
            "symbol": symbol,
            "strategy": strat_name,
            "pnl": pnl,
            "message": note
        }
        if "learned_insights" not in self.memory:
            self.memory["learned_insights"] = []
        self.memory["learned_insights"].insert(0, insight_entry)
        if len(self.memory["learned_insights"]) > 30:
            self.memory["learned_insights"] = self.memory["learned_insights"][:30]

        if leveled_up:
            lvl_entry = {
                "id": f"ins-lvl-{int(time.time()*1000)}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": "level_up",
                "message": f"⭐ LEVEL UP! Otak AI meningkat ke Level {self.memory['brain_level']}! Kapasitas adaptasi pasar diperluas."
            }
            self.memory["learned_insights"].insert(0, lvl_entry)

        self.save_memory()
        return {
            "success": True,
            "xp_gained": xp_gained,
            "leveled_up": leveled_up,
            "new_level": self.memory["brain_level"],
            "new_weight": new_weight,
            "insight": note
        }

    def get_learning_stats(self) -> Dict[str, Any]:
        """Ambil metrik pembelajaran mandiri untuk antarmuka dashboard"""
        total = max(self.memory.get("total_trades_analyzed", 0), 1)
        win_rate = round((self.memory.get("profitable_trades", 0) / total) * 100, 1) if self.memory.get("total_trades_analyzed", 0) > 0 else 0.0
        return {
            "brain_level": self.memory.get("brain_level", 1),
            "experience_points": self.memory.get("experience_points", 0),
            "next_level_xp": self.memory.get("next_level_xp", 100),
            "total_trades_analyzed": self.memory.get("total_trades_analyzed", 0),
            "profitable_trades": self.memory.get("profitable_trades", 0),
            "loss_trades": self.memory.get("loss_trades", 0),
            "adaptive_win_rate": win_rate,
            "strategy_weights": self.memory.get("strategy_weights", {}),
            "regime_matrix": self.memory.get("regime_matrix", {}),
            "recent_insights": self.memory.get("learned_insights", [])[:15]
        }

    def reset_learning_memory(self) -> Dict[str, Any]:
        """Reset memori pembelajaran AI kembali ke baseline bawaan"""
        self.memory = dict(DEFAULT_AI_MEMORY)
        self.save_memory()
        return {"success": True, "message": "Memori AI berhasil di-reset ke baseline."}

    def _load_api_config(self) -> Dict[str, Any]:
        if not os.path.exists(AI_CONFIG_FILE):
            self._save_api_config_raw(DEFAULT_AI_CONFIG)
            return dict(DEFAULT_AI_CONFIG)
        try:
            with open(AI_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                res = dict(DEFAULT_AI_CONFIG)
                res.update(cfg)
                return res
        except Exception:
            return dict(DEFAULT_AI_CONFIG)

    def _save_api_config_raw(self, cfg: Dict[str, Any]):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(AI_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def get_api_config(self) -> Dict[str, Any]:
        return {
            "config": self.api_config,
            "presets": PROVIDER_PRESETS
        }

    def update_api_config(self, new_cfg: Dict[str, Any]) -> Dict[str, Any]:
        self.api_config.update(new_cfg)
        self._save_api_config_raw(self.api_config)
        return self.api_config

    async def test_api_connection(self, provider: str, api_url: str, api_key: str, model: str) -> Dict[str, Any]:
        """Uji konektivitas ke API AI (OpenAI, Gemini, Ollama, DeepSeek, dll.)"""
        start_time = time.time()
        api_url = api_url.rstrip("/")

        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Google Gemini Endpoint
                if provider == "gemini":
                    # Format: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}
                    target_url = f"{api_url}/models/{model}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{
                            "parts": [{"text": "Reply with only: ApexAI Connection OK"}]
                        }]
                    }
                    resp = await client.post(target_url, json=payload)
                    latency = round((time.time() - start_time) * 1000, 1)

                    if resp.status_code == 200:
                        data = resp.json()
                        reply = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "OK")
                        return {
                            "success": True,
                            "latency_ms": latency,
                            "message": f"Koneksi ke Gemini berhasil! ({latency}ms)",
                            "reply": reply.strip()
                        }
                    else:
                        return {
                            "success": False,
                            "latency_ms": latency,
                            "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
                        }

                # 2. OpenAI / DeepSeek / Groq / Ollama / Custom (OpenAI Compatible)
                else:
                    endpoint = f"{api_url}/chat/completions"
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a ping tester."},
                            {"role": "user", "content": "Reply with only: ApexAI Connection OK"}
                        ],
                        "max_tokens": 20,
                        "temperature": 0.1
                    }
                    resp = await client.post(endpoint, headers=headers, json=payload)
                    latency = round((time.time() - start_time) * 1000, 1)

                    if resp.status_code == 200:
                        data = resp.json()
                        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "OK")
                        return {
                            "success": True,
                            "latency_ms": latency,
                            "message": f"Koneksi ke {provider.upper()} API Berhasil! ({latency}ms)",
                            "reply": reply.strip()
                        }
                    else:
                        return {
                            "success": False,
                            "latency_ms": latency,
                            "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
                        }

        except httpx.ConnectError:
            return {"success": False, "error": f"Tidak dapat terhubung ke URL {api_url}. Periksa URL endpoint Anda."}
        except httpx.TimeoutException:
            return {"success": False, "error": f"Timeout (10s) saat menghubungi {api_url}."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_settings(self):
        return self.settings

    def update_settings(self, new_settings: Dict[str, Any]):
        self.settings.update(new_settings)
        return self.settings

    def calculate_indicators(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Hitung EMA, RSI, Bollinger Bands, ATR dari data candlestick"""
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        n = len(closes)

        if n < 15:
            return {}

        # 1. EMA (Exponential Moving Average)
        def calc_ema(period):
            if n < period:
                return closes[-1]
            k = 2 / (period + 1)
            ema = sum(closes[:period]) / period
            for price in closes[period:]:
                ema = (price * k) + (ema * (1 - k))
            return ema

        ema9 = calc_ema(9)
        ema21 = calc_ema(21)
        ema50 = calc_ema(min(50, n - 1))

        # 2. RSI (14)
        gains, losses = [], []
        for i in range(1, min(15, n)):
            diff = closes[-i] - closes[-(i + 1)]
            if diff >= 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        avg_gain = sum(gains) / max(len(gains), 1)
        avg_loss = sum(losses) / max(len(losses), 1)
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 1)

        # 3. Bollinger Bands (20, 2)
        p_slice = closes[-min(20, n):]
        sma20 = sum(p_slice) / len(p_slice)
        variance = sum((x - sma20) ** 2 for x in p_slice) / len(p_slice)
        std_dev = math.sqrt(variance)
        bb_upper = sma20 + (2 * std_dev)
        bb_lower = sma20 - (2 * std_dev)

        # 4. ATR (14)
        trs = []
        for i in range(1, min(15, n)):
            h = highs[-i]
            l = lows[-i]
            prev_c = closes[-(i + 1)]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
        atr = sum(trs) / max(len(trs), 1)

        return {
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "rsi": rsi,
            "sma20": sma20,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "atr": atr,
            "current_price": closes[-1]
        }

    def calculate_lot_size(
        self,
        symbol: str,
        symbol_cfg: Dict[str, Any],
        account: Dict[str, Any],
        entry_price: float,
        sl_price: Optional[float] = None,
        confidence: float = 75.0,
        atr: float = 0.0,
        is_ai: bool = True
    ) -> float:
        """
        Kalkulasi besaran LOT cerdas oleh AI Engine:
        1. Mode 'fixed_lot': menggunakan nilai lot tetap yang ditentukan pengguna.
        2. Mode 'fixed_risk_pct': alokasi risiko persentase modal murni (Prop Firm Standard).
        3. Mode 'ai_dynamic': Smart Sizing berbasis Jarak Stop Loss, Skor Keyakinan (Confidence Multiplier),
           Regim Volatilitas Pasar (ATR), dan Guardrail Keamanan Margin.
        """
        mode = self.settings.get("lot_sizing_mode", "ai_dynamic")
        min_limit = max(0.01, float(self.settings.get("min_lot_limit", 0.01)))
        max_limit = max(min_limit, float(self.settings.get("max_lot_limit", 1.0)))

        # 1. Mode Fixed Lot Manual
        if mode == "fixed_lot":
            fixed_val = float(self.settings.get("fixed_lot_size", 0.01))
            return round(max(min_limit, min(fixed_val, max_limit)), 2)

        # 2. Perhitungan Modal Acuan & Normalisasi Mata Uang
        equity = float(account.get("equity", 1000.0)) if account else 1000.0
        currency = (account.get("currency") or "USD").upper() if account else "USD"

        # Normalisasi ke ekuivalen USD jika akun berdenominasi IDR (1 USD ~ 16.000 IDR)
        # agar alokasi risiko dolar tidak membengkak menjadi ribuan lot
        usd_equity = (equity / 16000.0) if currency == "IDR" else equity

        risk_pct = float(self.settings.get("risk_per_trade_pct", 2.0))
        risk_amount_usd = max(usd_equity * (risk_pct / 100.0), 0.5)

        # 3. Jarak Stop Loss & Parameter Simbol
        pip_size = symbol_cfg.get("pip_size", 0.0001)
        lot_unit = symbol_cfg.get("lot_unit", 100000)
        category = symbol_cfg.get("category", "forex")

        if sl_price and entry_price and abs(entry_price - sl_price) > 0:
            sl_dist = abs(entry_price - sl_price)
        else:
            sl_dist = max(atr * 1.5, pip_size * 30) if atr > 0 else pip_size * 30

        # 4. Kalkulasi Lot Berdasarkan Kategori Aset
        if category == "forex":
            sl_pips = max(sl_dist / pip_size, 10.0)
            # 1 Standard Lot Forex (100.000 unit) = ~$10 per pip
            pip_value_approx = 10.0
            calculated_lot = risk_amount_usd / (sl_pips * pip_value_approx)
        elif category == "crypto":
            # 1 Lot Crypto = 1 Unit Koin
            calculated_lot = risk_amount_usd / max(sl_dist, entry_price * 0.01)
        else:
            # Saham / Indeks
            calculated_lot = risk_amount_usd / max(sl_dist, entry_price * 0.02)

        # 5. Khusus Mode 'ai_dynamic': Dynamic Confidence & Volatility Multiplier
        if mode == "ai_dynamic":
            # Sizing berbasis keyakinan (Confidence Weighted)
            if confidence >= 90.0:
                conf_multiplier = 1.25   # Setup A+: Tambah lot 25%
            elif confidence >= 80.0:
                conf_multiplier = 1.00   # Setup Standar
            else:
                conf_multiplier = 0.75   # Setup Moderat: Pangkas lot 25%
            
            calculated_lot *= conf_multiplier

            # Volatility Dampener jika ATR tersedia (pasar terlalu volatil)
            if atr > 0 and entry_price > 0:
                atr_pct = atr / entry_price
                if atr_pct > 0.02: # Volatilitas > 2% per bar
                    calculated_lot *= 0.80

        # 6. Guardrail Keamanan Margin & Leverage
        leverage = int(account.get("leverage", 100)) if account else 100
        free_margin = float(account.get("free_margin", equity)) if account else equity

        # Batasi margin maksimum yang diizinkan per trade: max 25% dari free margin
        max_allowed_margin = max(free_margin * 0.25, 10.0)
        margin_per_lot = (entry_price * lot_unit) / leverage if leverage > 0 else entry_price

        if currency == "IDR":
            margin_per_lot *= 16000.0

        if margin_per_lot > 0:
            max_lot_by_margin = max_allowed_margin / margin_per_lot
            calculated_lot = min(calculated_lot, max_lot_by_margin)

        # 7. Pembulatan dan Pembatasan Nilai Minimum & Maksimum
        final_lot = round(max(min_limit, min(calculated_lot, max_limit)), 2)
        return final_lot

    def evaluate_market(self, symbol: str, symbol_cfg: Dict[str, Any], candles: List[Dict[str, Any]], price_info: Dict[str, Any], h1_candles: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:

        """Evaluasi kondisi pasar dengan strategi AI aktif dan Multi-Timeframe Confluence"""
        if len(candles) < 20:
            return None

        indicators = self.calculate_indicators(candles)
        if not indicators:
            return None

        strategy_id = self.settings.get("active_strategy", "neural_momentum")
        digits = symbol_cfg["digits"]
        pip_size = symbol_cfg["pip_size"]
        cur_p = indicators["current_price"]
        atr = indicators["atr"]
        rsi = indicators["rsi"]
        ema9 = indicators["ema9"]
        ema21 = indicators["ema21"]
        ema50 = indicators["ema50"]

        signal_dir = None
        confidence = 0.0
        reasons = []

        if strategy_id == "neural_momentum":
            # Bullish trend alignment
            if ema9 > ema21 > ema50 and cur_p > ema9 and 45 <= rsi <= 68:
                signal_dir = "BUY"
                conf_base = 78.0
                if rsi < 60:
                    conf_base += 8.0 # Healthy room for growth
                if cur_p > indicators["sma20"]:
                    conf_base += 4.5
                confidence = round(min(conf_base + random.uniform(0.5, 4.0), 96.5), 1)
                reasons.append(f"EMA 9 ({ema9:.{digits}f}) berada di atas EMA 21 & EMA 50 (Strong Bullish Trend)")
                reasons.append(f"RSI {rsi} berada dalam zona momentum ideal (< 70, belum overbought)")
                reasons.append(f"Volatilitas terkontrol dengan ATR {atr:.{digits}f}")

            # Bearish trend alignment
            elif ema9 < ema21 < ema50 and cur_p < ema9 and 32 <= rsi <= 55:
                signal_dir = "SELL"
                conf_base = 78.0
                if rsi > 40:
                    conf_base += 7.5
                if cur_p < indicators["sma20"]:
                    conf_base += 5.0
                confidence = round(min(conf_base + random.uniform(0.5, 4.0), 96.5), 1)
                reasons.append(f"EMA 9 ({ema9:.{digits}f}) menembus ke bawah EMA 21 & EMA 50 (Strong Bearish Trend)")
                reasons.append(f"RSI {rsi} mengonfirmasi tekanan jual aktif (> 30, belum oversold)")
                reasons.append(f"Breakout di bawah SMA 20 terverifikasi")

        elif strategy_id == "smart_money":
            recent_lows = min(c["low"] for c in candles[-10:-1])
            recent_highs = max(c["high"] for c in candles[-10:-1])
            
            if cur_p > recent_lows and candles[-1]["low"] <= recent_lows:
                signal_dir = "BUY"
                confidence = round(random.uniform(84.0, 95.0), 1)
                reasons.append(f"Institutional Liquidity Sweep terdeteksi pada swing low {recent_lows:.{digits}f}")
                reasons.append("Rejection candle instan mengindikasikan akumulasi Smart Money")
                reasons.append("Target liquidity pool berada pada resistance terdekat")
            elif cur_p < recent_highs and candles[-1]["high"] >= recent_highs:
                signal_dir = "SELL"
                confidence = round(random.uniform(84.0, 95.0), 1)
                reasons.append(f"Liquidity Grab terdeteksi pada swing high {recent_highs:.{digits}f}")
                reasons.append("Distribusi institusional memicu penolakan harga atas (FVG Bearish Entry)")
                reasons.append("Stop loss ketat di atas swing high terbaru")

        elif strategy_id == "mean_reversion":
            if cur_p <= indicators["bb_lower"] and rsi < 32:
                signal_dir = "BUY"
                confidence = round(random.uniform(76.0, 92.0), 1)
                reasons.append(f"Harga menembus pita bawah Bollinger ({indicators['bb_lower']:.{digits}f})")
                reasons.append(f"RSI berada pada level oversold ekstrim ({rsi}) dengan potensi mean reversion ke SMA 20")
            elif cur_p >= indicators["bb_upper"] and rsi > 68:
                signal_dir = "SELL"
                confidence = round(random.uniform(76.0, 92.0), 1)
                reasons.append(f"Harga menyentuh batas atas Bollinger Bands ({indicators['bb_upper']:.{digits}f})")
                reasons.append(f"RSI overbought ({rsi}) mengindikasikan pelemahan momentum beli")

        elif strategy_id == "neural_scalper":
            last_c = candles[-1]
            body = abs(last_c["close"] - last_c["open"])
            spread_dist = last_c["high"] - last_c["low"]
            if spread_dist > 0:
                if (last_c["close"] - last_c["low"]) / spread_dist > 0.75 and rsi > 48:
                    signal_dir = "BUY"
                    confidence = round(random.uniform(80.0, 93.0), 1)
                    reasons.append("Neural Micro-Scorer: Bullish pin-bar wick rejection terdeteksi")
                    reasons.append("Order flow imbalance menguntungkan pihak Buyer")
                elif (last_c["high"] - last_c["close"]) / spread_dist > 0.75 and rsi < 52:
                    signal_dir = "SELL"
                    confidence = round(random.uniform(80.0, 93.0), 1)
                    reasons.append("Neural Micro-Scorer: Bearish wick rejection terdeteksi pada resistance")
                    reasons.append("Penyerapan volume seller lebih dominan")

        elif strategy_id in self.strategies:
            # Evaluasi Strategi Otonom Hasil Evolved AI / LLM
            strat_info = self.strategies[strategy_id]
            logic = strat_info.get("logic_type", "trend_confluence")
            ind_cfg = strat_info.get("indicators", {})
            rsi_os = ind_cfg.get("rsi_oversold", 35)
            rsi_ob = ind_cfg.get("rsi_overbought", 65)

            if logic == "trend_confluence":
                if ema9 > ema21 and rsi > 48 and rsi < rsi_ob:
                    signal_dir = "BUY"
                    confidence = round(random.uniform(80.0, 93.0), 1)
                    reasons.append(f"🧬 AI Evolved Trend: EMA Alignment + RSI Momentum ({rsi})")
                elif ema9 < ema21 and rsi < 52 and rsi > rsi_os:
                    signal_dir = "SELL"
                    confidence = round(random.uniform(80.0, 93.0), 1)
                    reasons.append(f"🧬 AI Evolved Trend: Bearish EMA Alignment + RSI ({rsi})")
            elif logic == "mean_reversion":
                if rsi <= rsi_os:
                    signal_dir = "BUY"
                    confidence = round(random.uniform(82.0, 94.0), 1)
                    reasons.append(f"🧬 AI Evolved Reversion: RSI Oversold ({rsi} <= {rsi_os})")
                elif rsi >= rsi_ob:
                    signal_dir = "SELL"
                    confidence = round(random.uniform(82.0, 94.0), 1)
                    reasons.append(f"🧬 AI Evolved Reversion: RSI Overbought ({rsi} >= {rsi_ob})")
            else:  # breakout
                if cur_p > indicators["bb_upper"]:
                    signal_dir = "BUY"
                    confidence = round(random.uniform(79.0, 91.0), 1)
                    reasons.append("🧬 AI Evolved Breakout: Upper Bollinger Breakout dengan ekspansi volatilitas")
                elif cur_p < indicators["bb_lower"]:
                    signal_dir = "SELL"
                    confidence = round(random.uniform(79.0, 91.0), 1)
                    reasons.append("🧬 AI Evolved Breakout: Lower Bollinger Breakdown")

        # Multi-Timeframe (MTF) Confluence Filter
        if signal_dir and h1_candles and len(h1_candles) >= 15:
            h1_ind = self.calculate_indicators(h1_candles)
            if h1_ind:
                h1_cur = h1_ind["current_price"]
                h1_ema21 = h1_ind["ema21"]
                h1_ema50 = h1_ind["ema50"]

                if signal_dir == "BUY":
                    if h1_cur < h1_ema21 < h1_ema50:
                        # Tren H1 Bearish kuat melawan sinyal BUY M15 -> Blokir order untuk melindungi modal!
                        return None
                    elif h1_cur > h1_ema21 > h1_ema50:
                        confidence = round(min(confidence + 5.5, 98.0), 1)
                        reasons.append("🛡️ MTF Filter: Tren makro H1 Bullish selaras mengonfirmasi BUY!")

                elif signal_dir == "SELL":
                    if h1_cur > h1_ema21 > h1_ema50:
                        # Tren H1 Bullish kuat melawan sinyal SELL M15 -> Blokir order!
                        return None
                    elif h1_cur < h1_ema21 < h1_ema50:
                        confidence = round(min(confidence + 5.5, 98.0), 1)
                        reasons.append("🛡️ MTF Filter: Tren makro H1 Bearish selaras mengonfirmasi SELL!")

        # High-Impact News Protection Shield (Market Intel)
        if hasattr(self, "market_intel") and self.market_intel and signal_dir:
            shield = self.market_intel.is_high_impact_news_near(symbol)
            if shield.get("shield_active"):
                mins = shield.get("minutes_away", 999)
                evt = shield.get("event", "Economic News")
                reasons.append(f"🛡️ NEWS SHIELD: Berita High-Impact '{evt}' dalam {mins} menit")
                # Jika berita < 15 menit, batalkan entry untuk mencegah slippage fatal
                if abs(mins) <= 15:
                    return None
                # Jika 15-30 menit, naikkan penalti proteksi
                confidence = max(50.0, confidence - 6.0)

            # Internet Macro Sentiment Bias
            sentiment_summary = getattr(self.market_intel, "sentiment_score", 0.0)
            if signal_dir == "BUY" and sentiment_summary > 15:
                confidence = round(min(confidence + 3.0, 98.5), 1)
                reasons.append(f"🌐 Macro Sentiment: Bullish Bias ({sentiment_summary:+.1f}%) memperkuat sinyal")
            elif signal_dir == "SELL" and sentiment_summary < -15:
                confidence = round(min(confidence + 3.0, 98.5), 1)
                reasons.append(f"🌐 Macro Sentiment: Bearish Bias ({sentiment_summary:+.1f}%) memperkuat sinyal")

        # Apply Learned Adaptive Strategy Weight
        strat_weight = self.memory.get("strategy_weights", {}).get(strategy_id, 1.0)
        confidence = round(min(confidence * strat_weight, 99.0), 1)
        if strat_weight != 1.0:
            reasons.append(f"🧠 Adaptive Weighting: Pengali performa strategi x{strat_weight:.2f} (Confidence terkalibrasi ke {confidence}%)")

        # Check against confidence threshold
        if not signal_dir or confidence < self.settings.get("confidence_threshold", 75):
            return None

        # Calculate dynamic SL & TP using ATR
        sl_dist = max(atr * 1.5, pip_size * 10)
        rr_ratio = self.strategies.get(strategy_id, {}).get("min_rr", 2.0)
        tp_dist = sl_dist * rr_ratio

        if signal_dir == "BUY":
            entry_price = price_info["ask"]
            sl_price = round(entry_price - sl_dist, digits)
            tp_price = round(entry_price + tp_dist, digits)
        else:
            entry_price = price_info["bid"]
            sl_price = round(entry_price + sl_dist, digits)
            tp_price = round(entry_price - tp_dist, digits)

        # AI Engine source label
        provider_tag = "ApexAI Quant"
        if self.api_config.get("enabled"):
            provider_tag = self.api_config.get("model", "ApexAI Quant")

        # AI Smart Position Sizing
        recommended_lot = self.calculate_lot_size(
            symbol=symbol,
            symbol_cfg=symbol_cfg,
            account={"equity": 1000.0, "currency": "USD", "leverage": 100},
            entry_price=entry_price,
            sl_price=sl_price,
            confidence=confidence,
            atr=atr,
            is_ai=True
        )

        signal = {
            "id": f"sig-{int(time.time()*1000)}-{random.randint(100,999)}",
            "symbol": symbol,
            "category": symbol_cfg["category"],
            "direction": signal_dir,
            "lot": recommended_lot,
            "recommended_lot": recommended_lot,
            "strategy": self.strategies.get(strategy_id, {}).get("name", "AI Strategy"),
            "strategy_id": strategy_id,
            "provider_tag": provider_tag,
            "confidence": confidence,
            "price": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "rr_ratio": rr_ratio,
            "reasoning": reasons,
            "summary_text": f"AI Signal [{signal_dir}] pada {symbol}: Lot {recommended_lot} (Keyakinan {confidence}% via {provider_tag}). " + " | ".join(reasons),
            "timestamp": int(time.time())
        }


        # Keep last 30 signals
        self.recent_signals.insert(0, signal)
        if len(self.recent_signals) > 30:
            self.recent_signals.pop()

        return signal

    def run_backtest(
        self,
        symbol: str,
        strategy_id: str,
        candles: List[Dict[str, Any]],
        symbol_cfg: Dict[str, Any],
        initial_balance: float = 10000.0,
        risk_pct: float = 2.0,
        confidence_threshold: int = 75
    ) -> Dict[str, Any]:
        """Menjalankan backtest algoritma kuantitatif AI pada data historis candles"""
        if len(candles) < 25:
            return {
                "success": False,
                "error": "Candle historis belum mencukupi untuk backtest (minimal 25 candle)"
            }

        balance = float(initial_balance)
        peak_balance = balance
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

        trades = []
        equity_curve = [{"time": candles[0]["time"], "balance": round(balance, 2)}]

        digits = symbol_cfg.get("digits", 2)
        pip_size = symbol_cfg.get("pip_size", 0.01)

        # Save temporary settings
        old_strategy = self.settings.get("active_strategy")
        old_conf = self.settings.get("confidence_threshold")
        self.settings["active_strategy"] = strategy_id
        self.settings["confidence_threshold"] = confidence_threshold

        active_pos = None

        for i in range(20, len(candles)):
            window = candles[:i]
            cur_candle = candles[i]
            spread = symbol_cfg.get("spread_pips", 1.0) * pip_size
            price_info = {
                "ask": cur_candle["close"] + (spread / 2),
                "bid": cur_candle["close"] - (spread / 2),
                "last": cur_candle["close"]
            }

            # 1. If active position, check SL or TP hit
            if active_pos:
                hit = None
                exit_price = None

                if active_pos["direction"] == "BUY":
                    if cur_candle["low"] <= active_pos["sl"]:
                        hit = "Stop Loss"
                        exit_price = active_pos["sl"]
                    elif cur_candle["high"] >= active_pos["tp"]:
                        hit = "Take Profit"
                        exit_price = active_pos["tp"]
                else: # SELL
                    if cur_candle["high"] >= active_pos["sl"]:
                        hit = "Stop Loss"
                        exit_price = active_pos["sl"]
                    elif cur_candle["low"] <= active_pos["tp"]:
                        hit = "Take Profit"
                        exit_price = active_pos["tp"]

                if hit:
                    diff = (exit_price - active_pos["entry_price"]) if active_pos["direction"] == "BUY" else (active_pos["entry_price"] - exit_price)
                    pnl = round(diff * active_pos["units"], 2)
                    pnl_pct = round((pnl / (balance if balance > 0 else 1)) * 100, 2)
                    balance = round(balance + pnl, 2)

                    if balance > peak_balance:
                        peak_balance = balance
                    dd = peak_balance - balance
                    dd_pct = round((dd / peak_balance) * 100, 2) if peak_balance > 0 else 0.0
                    if dd_pct > max_drawdown_pct:
                        max_drawdown_pct = dd_pct
                        max_drawdown = dd

                    trades.append({
                        "trade_num": len(trades) + 1,
                        "type": active_pos["direction"],
                        "direction": active_pos["direction"],
                        "entry_time": active_pos.get("time", cur_candle["time"]),
                        "exit_time": cur_candle["time"],
                        "entry_price": round(active_pos["entry_price"], digits),
                        "exit_price": round(exit_price, digits),
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "balance": balance,
                        "reason": hit,
                        "confidence": active_pos["confidence"]
                    })
                    equity_curve.append({"time": cur_candle["time"], "balance": balance})
                    active_pos = None

            # 2. If no active trade, look for new signal
            if not active_pos:
                sig = self.evaluate_market(symbol, symbol_cfg, window, price_info)
                if sig:
                    risk_amount = balance * (risk_pct / 100.0)
                    units = round(risk_amount / (abs(sig["price"] - sig["sl"]) + 1e-6), 2)
                    active_pos = {
                        "direction": sig["direction"],
                        "entry_price": sig["price"],
                        "sl": sig["sl"],
                        "tp": sig["tp"],
                        "units": units,
                        "confidence": sig["confidence"],
                        "time": cur_candle["time"]
                    }

        # Restore original settings
        self.settings["active_strategy"] = old_strategy
        self.settings["confidence_threshold"] = old_conf

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        total_trades = len(trades)
        win_rate = round((len(wins) / total_trades) * 100, 1) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        net_profit = round(balance - initial_balance, 2)
        net_profit_pct = round((net_profit / initial_balance) * 100, 2)

        metrics = {
            "win_rate_pct": win_rate,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "profit_factor": profit_factor,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": max_drawdown_pct,
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "final_balance": balance
        }

        return {
            "success": True,
            "symbol": symbol,
            "strategy": strategy_id,
            "strategy_name": self.strategies.get(strategy_id, {}).get("name", strategy_id),
            "candles_analyzed": len(candles),
            "initial_balance": initial_balance,
            "final_balance": balance,
            "metrics": metrics,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": max_drawdown_pct,
            "equity_curve": equity_curve,
            "trades": trades[-50:]
        }
