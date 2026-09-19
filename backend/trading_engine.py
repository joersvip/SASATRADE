import os
import json
import time
import uuid
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("trading_engine")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TRADES_FILE = os.path.join(DATA_DIR, "trades.json")

class TradingEngine:
    def __init__(self, account_mgr, market_feed, ai_engine, mt5_bridge=None):
        self.account_mgr = account_mgr
        self.market_feed = market_feed
        self.ai_engine = ai_engine
        self.mt5_bridge = mt5_bridge
        
        self.positions: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self.last_ai_scan_time = 0
        
        # Risk Circuit Breaker & Kill Switch
        self.circuit_breaker_tripped = False
        self.circuit_breaker_reason = ""
        self.daily_start_balances: Dict[str, float] = {}
        self.current_trading_day = time.strftime("%Y-%m-%d")

        self._load_trades()
        self.log_event("Production Engine Diinisialisasi - Siap Menerima Order Riil", level="info")

    def _load_trades(self):
        if os.path.exists(TRADES_FILE):
            try:
                with open(TRADES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.positions = data.get("positions", [])
                    self.history = data.get("history", [])
            except Exception:
                self.positions = []
                self.history = []
        else:
            self._save_trades()

    def _save_trades(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "positions": self.positions,
                "history": self.history
            }, f, indent=2)

    def log_event(self, message: str, level: str = "info", symbol: str = None):
        entry = {
            "id": f"log-{int(time.time()*1000)}",
            "time": time.strftime("%H:%M:%S"),
            "message": message,
            "level": level,
            "symbol": symbol
        }
        self.logs.insert(0, entry)
        if len(self.logs) > 60:
            self.logs.pop()

    def open_position(self, account_id: str, symbol: str, direction: str, lot: float = None, 
                      sl: float = None, tp: float = None, strategy: str = "Manual", 
                      is_ai: bool = False, reasoning: str = None) -> Dict[str, Any]:
        
        if self.circuit_breaker_tripped:
            return {
                "success": False,
                "error": f"🚨 Circuit Breaker Aktif ({self.circuit_breaker_reason}). Transaksi baru dikunci untuk melindungi modal!"
            }

        acc = None
        for a in self.account_mgr.get_all():
            if a["id"] == account_id:
                acc = a
                break
        if not acc:
            return {"success": False, "error": "Akun tidak ditemukan"}

        cfg = self.market_feed.get_symbol_info(symbol)
        digits = cfg["digits"]
        price_info = self.market_feed.prices.get(symbol)
        if not price_info:
            return {"success": False, "error": f"Simbol {symbol} tidak valid"}

        entry_price = price_info["ask"] if direction == "BUY" else price_info["bid"]

        # Dynamic SL and TP
        pip = cfg["pip_size"]
        if not sl:
            sl = round(entry_price - (pip * 30) if direction == "BUY" else entry_price + (pip * 30), digits)
        if not tp:
            tp = round(entry_price + (pip * 60) if direction == "BUY" else entry_price - (pip * 60), digits)

        # Penentuan Besaran Lot Cerdas oleh AI Engine (Smart Dynamic Lot Sizing)
        if not lot or lot <= 0 or is_ai:
            lot = self.ai_engine.calculate_lot_size(
                symbol=symbol,
                symbol_cfg=cfg,
                account=acc,
                entry_price=entry_price,
                sl_price=sl,
                confidence=80.0,
                is_ai=is_ai
            )

        # Margin calculation & Currency Normalization
        leverage = acc.get("leverage", 100) or 100
        contract_value_usd = entry_price * lot * cfg["lot_unit"]
        required_margin_usd = contract_value_usd / leverage
        
        # Jika akun IDR, margin yang diperlukan dihitung dalam IDR
        acc_currency = (acc.get("currency") or "USD").upper()
        if acc_currency == "IDR":
            required_margin = round(required_margin_usd * 16000.0, 2)
            curr_symbol = "Rp"
        else:
            required_margin = round(required_margin_usd, 2)
            curr_symbol = "$"

        if acc.get("free_margin", 0.0) < required_margin and not (acc.get("mode") == "real" and acc.get("type") == "mt5"):
            return {"success": False, "error": f"Free margin tidak mencukupi (Perlu: {curr_symbol} {required_margin:,.2f}, Tersedia: {curr_symbol} {acc['free_margin']:,.2f})"}

        # Real Execution via MT5 Broker if connected

        ticket = None
        if acc.get("mode") == "real" and acc.get("type") == "mt5" and self.mt5_bridge and self.mt5_bridge.connected:
            mt5_res = self.mt5_bridge.send_order(
                symbol=symbol,
                direction=direction,
                volume=lot,
                sl=sl or 0.0,
                tp=tp or 0.0,
                comment=f"ApexAI {'AI' if is_ai else 'Man'}"
            )
            if not mt5_res.get("success"):
                return {"success": False, "error": f"Eksekusi Broker MT5 Gagal: {mt5_res.get('error')}"}
            ticket = mt5_res.get("ticket")
            entry_price = mt5_res.get("price", entry_price)

        pos_id = f"pos-{uuid.uuid4().hex[:8]}"
        pos = {
            "id": pos_id,
            "ticket": ticket,
            "account_id": account_id,
            "mode": acc.get("mode", "demo"),
            "symbol": symbol,
            "direction": direction,
            "lot": lot,
            "units": lot * cfg["lot_unit"],
            "entry_price": entry_price,
            "current_price": entry_price,
            "sl": sl,
            "tp": tp,
            "margin": required_margin,
            "pnl": 0.0,
            "pips": 0.0,
            "open_time": int(time.time()),
            "strategy": strategy,
            "is_ai": is_ai,
            "reasoning": reasoning or ("Eksekusi Manual" if not is_ai else "Sinyal AI")
        }

        self.positions.append(pos)
        self._save_trades()

        mode_tag = "AKUN REAL" if acc.get("mode") == "real" else "DEMO"
        self.log_event(
            f"[{mode_tag}] [{ 'ROBOT AI' if is_ai else 'MANUAL' }] Order {direction} {symbol} dibuka @ {entry_price:.{digits}f} (Lot: {lot})",
            level="success" if direction == "BUY" else "warning",
            symbol=symbol
        )

        self._recalculate_account(account_id)
        return {"success": True, "position": pos}

    def close_position(self, position_id: str, reason: str = "Manual Close") -> Dict[str, Any]:
        pos = None
        for p in self.positions:
            if p["id"] == position_id:
                pos = p
                break
        if not pos:
            return {"success": False, "error": "Posisi tidak ditemukan"}

        # Real close on MT5 if ticket exists
        if pos.get("ticket") and self.mt5_bridge and self.mt5_bridge.connected:
            try:
                self.mt5_bridge.close_order(pos["ticket"], pos["symbol"], pos["direction"], pos["lot"])
            except Exception as e:
                logger.error(f"Error closing MT5 position: {e}")

        self.positions.remove(pos)

        cfg = self.market_feed.get_symbol_info(pos["symbol"])
        digits = cfg["digits"]
        exit_price = pos["current_price"]
        pnl = pos["pnl"]

        hist_item = {
            "id": pos["id"],
            "ticket": pos.get("ticket"),
            "account_id": pos["account_id"],
            "mode": pos.get("mode", "demo"),
            "symbol": pos["symbol"],
            "direction": pos["direction"],
            "lot": pos["lot"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "pnl": pnl,
            "sl": pos["sl"],
            "tp": pos["tp"],
            "open_time": pos["open_time"],
            "close_time": int(time.time()),
            "close_reason": reason,
            "strategy": pos["strategy"],
            "is_ai": pos["is_ai"]
        }
        self.history.insert(0, hist_item)
        self._save_trades()

        acc = None
        for a in self.account_mgr.get_all():
            if a["id"] == pos["account_id"]:
                acc = a
                break
        if acc:
            new_balance = round(acc["balance"] + pnl, 2)
            self.account_mgr.update_metrics(acc["id"], balance=new_balance)
            self._recalculate_account(acc["id"])

        self.log_event(
            f"Posisi {pos['symbol']} ditutup @ {exit_price:.{digits}f} | Net PnL: {'+' if pnl >= 0 else ''}${pnl:.2f} ({reason})",
            level="success" if pnl >= 0 else "error",
            symbol=pos["symbol"]
        )

        # Trigger Self-Learning Feedback Loop
        try:
            learn_res = self.ai_engine.learn_from_trade(hist_item)
            if learn_res.get("leveled_up"):
                self.log_event(f"⭐ AI BRAIN LEVEL UP! Tingkat kecerdasan naik ke Level {learn_res['new_level']}!", level="warning")
        except Exception as e:
            logger.error(f"Error in learn_from_trade: {e}")

        return {"success": True, "trade": hist_item}

    def close_all(self, account_id: str = None) -> int:
        to_close = [p["id"] for p in self.positions if not account_id or p["account_id"] == account_id]
        count = 0
        for pid in to_close:
            res = self.close_position(pid, reason="Close All Executed")
            if res.get("success"):
                count += 1
        return count

    def modify_position(self, position_id: str, sl: float, tp: float):
        for p in self.positions:
            if p["id"] == position_id:
                p["sl"] = float(sl)
                p["tp"] = float(tp)
                self._save_trades()
                self.log_event(f"SL/TP Posisi {p['symbol']} diubah (SL: {sl}, TP: {tp})", level="info", symbol=p["symbol"])
                return {"success": True, "position": p}
    def _sync_mt5_live_positions(self, acc_id: str):
        """Sinkronisasi dua arah posisi terbuka riil dari terminal MT5 Exness."""
        if not self.mt5_bridge or not self.mt5_bridge.connected:
            return

        try:
            real_positions = self.mt5_bridge.get_real_open_positions()
            real_tickets = {p["ticket"]: p for p in real_positions}

            current_acc_positions = [p for p in self.positions if p.get("account_id") == acc_id]
            current_ticket_map = {p.get("ticket"): p for p in current_acc_positions if p.get("ticket")}

            has_changes = False

            # 1. Update atau tambahkan posisi riil dari broker
            for ticket, real_pos in real_tickets.items():
                if ticket in current_ticket_map:
                    existing = current_ticket_map[ticket]
                    existing["current_price"] = real_pos["current_price"]
                    existing["pnl"] = real_pos["pnl"]
                    existing["sl"] = real_pos["sl"]
                    existing["tp"] = real_pos["tp"]
                else:
                    sym = real_pos["clean_symbol"]
                    cfg = self.market_feed.get_symbol_info(sym)
                    new_pos = {
                        "id": f"mt5-{ticket}",
                        "ticket": ticket,
                        "account_id": acc_id,
                        "mode": "real",
                        "symbol": sym,
                        "broker_symbol": real_pos["symbol"],
                        "direction": real_pos["direction"],
                        "lot": real_pos["lot"],
                        "units": real_pos["lot"] * cfg["lot_unit"],
                        "entry_price": real_pos["entry_price"],
                        "current_price": real_pos["current_price"],
                        "sl": real_pos["sl"],
                        "tp": real_pos["tp"],
                        "margin": 0.0,
                        "pnl": real_pos["pnl"],
                        "pips": 0.0,
                        "open_time": real_pos["open_time"],
                        "strategy": "Exness / MT5 Terminal",
                        "is_ai": False,
                        "reasoning": "Posisi riil broker tersinkronisasi"
                    }
                    self.positions.append(new_pos)
                    has_changes = True

            # 2. Deteksi posisi yang sudah ditutup di broker (SL/TP/Manual close di Exness)
            for existing in list(current_acc_positions):
                t = existing.get("ticket")
                if t and t not in real_tickets:
                    self.positions.remove(existing)
                    self.history.insert(0, {
                        "id": existing["id"],
                        "ticket": t,
                        "account_id": acc_id,
                        "mode": "real",
                        "symbol": existing["symbol"],
                        "direction": existing["direction"],
                        "lot": existing["lot"],
                        "entry_price": existing["entry_price"],
                        "exit_price": existing.get("current_price", existing["entry_price"]),
                        "pnl": existing.get("pnl", 0.0),
                        "sl": existing.get("sl"),
                        "tp": existing.get("tp"),
                        "open_time": existing.get("open_time", int(time.time())),
                        "close_time": int(time.time()),
                        "close_reason": "Posisi ditutup di terminal broker MT5 (SL/TP/Manual)",
                        "strategy": existing.get("strategy", "Exness"),
                        "is_ai": existing.get("is_ai", False)
                    })
                    has_changes = True

            if has_changes:
                self._save_trades()
        except Exception as e:
            logger.error(f"Error pada _sync_mt5_live_positions: {e}")

    def tick_cycle(self):
        """Siklus evaluasi produksi"""
        self.market_feed.tick()
        now = int(time.time())
        ai_settings = self.ai_engine.get_settings()
        trailing_enabled = ai_settings.get("trailing_stop_enabled", True)

        # 1. Update Open Positions
        positions_to_close = []
        for pos in self.positions:
            symbol = pos["symbol"]
            cfg = self.market_feed.get_symbol_info(symbol)
            p_info = self.market_feed.prices.get(symbol)
            if not p_info:
                continue

            bid = p_info["bid"]
            ask = p_info["ask"]
            digits = cfg["digits"]
            pip = cfg["pip_size"]

            if pos["direction"] == "BUY":
                pos["current_price"] = bid
                diff = bid - pos["entry_price"]
                pnl = round(diff * pos["units"], 2)
                pips = round(diff / pip, 1)

                if pos["sl"] and bid <= pos["sl"]:
                    positions_to_close.append((pos["id"], "Stop Loss Hit"))
                elif pos["tp"] and bid >= pos["tp"]:
                    positions_to_close.append((pos["id"], "Take Profit Hit"))
                elif trailing_enabled and pips > 25:
                    new_sl = round(bid - (pip * 15), digits)
                    if not pos["sl"] or new_sl > pos["sl"]:
                        pos["sl"] = new_sl

            else: # SELL
                pos["current_price"] = ask
                diff = pos["entry_price"] - ask
                pnl = round(diff * pos["units"], 2)
                pips = round(diff / pip, 1)

                if pos["sl"] and ask >= pos["sl"]:
                    positions_to_close.append((pos["id"], "Stop Loss Hit"))
                elif pos["tp"] and ask <= pos["tp"]:
                    positions_to_close.append((pos["id"], "Take Profit Hit"))
                elif trailing_enabled and pips > 25:
                    new_sl = round(ask + (pip * 15), digits)
                    if not pos["sl"] or new_sl < pos["sl"]:
                        pos["sl"] = new_sl

            pos["pnl"] = pnl
            pos["pips"] = pips

        for pid, reason in positions_to_close:
            self.close_position(pid, reason=reason)

        # 2. Sinkronisasi Akun & Posisi Riil MT5 Broker & Proteksi Circuit Breaker Harian
        active_acc = self.account_mgr.get_active()
        if active_acc:
            acc_id = active_acc["id"]
            if active_acc.get("mode") == "real" and active_acc.get("type") == "mt5" and self.mt5_bridge and self.mt5_bridge.connected:
                real_metrics = self.mt5_bridge.get_real_account_metrics()
                if real_metrics:
                    self.account_mgr.update_metrics(
                        acc_id,
                        balance=real_metrics["balance"],
                        equity=real_metrics["equity"],
                        margin=real_metrics["margin"],
                        free_margin=real_metrics.get("free_margin"),
                        margin_level=real_metrics.get("margin_level")
                    )
                # Sinkronkan posisi terbuka riil dari broker MT5
                self._sync_mt5_live_positions(acc_id)
            else:
                self._recalculate_account(acc_id)

            # Inisialisasi saldo awal hari jika belum ada
            if acc_id not in self.daily_start_balances:
                self.daily_start_balances[acc_id] = active_acc["balance"]

            # Pemeriksaan Maksimum Kerugian Harian (Max Daily Drawdown)
            start_bal = self.daily_start_balances.get(acc_id, active_acc["balance"])

            curr_equity = active_acc["equity"]
            if start_bal > 0 and not self.circuit_breaker_tripped:
                daily_loss = start_bal - curr_equity
                daily_loss_pct = round((daily_loss / start_bal) * 100, 2)
                max_loss_limit = ai_settings.get("daily_loss_limit_pct", 5.0)

                if daily_loss_pct >= max_loss_limit:
                    self.circuit_breaker_tripped = True
                    self.circuit_breaker_reason = f"Batas Kerugian Harian Tercapai (-{daily_loss_pct}% >= batas -{max_loss_limit}%)"
                    self.close_all(acc_id)
                    self.ai_engine.settings["mode"] = "off"
                    self.log_event(
                        f"🚨 CIRCUIT BREAKER TRIP: {self.circuit_breaker_reason}. Seluruh posisi ditutup & Robot AI dinonaktifkan otomatis!",
                        level="error"
                    )

        # 3. AI Robot Auto Execution (Hanya jika Circuit Breaker tidak aktif)
        if not self.circuit_breaker_tripped and ai_settings.get("mode") == "auto" and (now - self.last_ai_scan_time >= 5):
            self.last_ai_scan_time = now
            self._run_ai_auto_scan()

    def trigger_kill_switch(self) -> Dict[str, Any]:
        """Emergency Kill Switch: Tutup semua posisi seketika dan kunci robot AI"""
        closed_count = self.close_all()
        self.circuit_breaker_tripped = True
        self.circuit_breaker_reason = "Emergency Kill-Switch Diaktifkan Manual"
        self.ai_engine.settings["mode"] = "off"
        self.log_event(
            f"🛑 EMERGENCY KILL-SWITCH DIAKTIFKAN: {closed_count} posisi ditutup & Robot AI dinonaktifkan seketika.",
            level="error"
        )
        return {
            "success": True,
            "closed_count": closed_count,
            "message": "Kill-switch berhasil dieksekusi. Semua posisi telah ditutup dan sistem dikunci."
        }

    def reset_circuit_breaker(self) -> Dict[str, Any]:
        """Reset Circuit Breaker manual agar sistem bisa trading kembali"""
        self.circuit_breaker_tripped = False
        self.circuit_breaker_reason = ""
        active_acc = self.account_mgr.get_active()
        if active_acc:
            self.daily_start_balances[active_acc["id"]] = active_acc["balance"]
        self.log_event("Circuit Breaker berhasil dibuka kembali secara manual.", level="info")
        return {"success": True, "message": "Circuit breaker telah direset. Mode trading normal kembali."}

    def get_circuit_breaker_status(self, account_id: str = None) -> Dict[str, Any]:
        active_acc = self.account_mgr.get_active()
        acc = active_acc if (not account_id and active_acc) else next((a for a in self.account_mgr.get_all() if a["id"] == account_id), None)
        
        daily_loss_pct = 0.0
        if acc:
            start_bal = self.daily_start_balances.get(acc["id"], acc["balance"])
            if start_bal > 0:
                daily_loss = start_bal - acc["equity"]
                daily_loss_pct = round((daily_loss / start_bal) * 100, 2)

        return {
            "tripped": self.circuit_breaker_tripped,
            "reason": self.circuit_breaker_reason,
            "daily_loss_pct": daily_loss_pct,
            "daily_loss_limit_pct": self.ai_engine.settings.get("daily_loss_limit_pct", 5.0)
        }

    def _recalculate_account(self, account_id: str):
        acc = None
        for a in self.account_mgr.get_all():
            if a["id"] == account_id:
                acc = a
                break
        if not acc:
            return

        total_margin = 0.0
        total_floating_pnl = 0.0

        for p in self.positions:
            if p["account_id"] == account_id:
                total_margin += p.get("margin", 0.0)
                total_floating_pnl += p.get("pnl", 0.0)

        equity = round(acc["balance"] + total_floating_pnl, 2)
        self.account_mgr.update_metrics(account_id, equity=equity, margin=total_margin)

    def _run_ai_auto_scan(self):
        if self.circuit_breaker_tripped:
            return

        active_acc = self.account_mgr.get_active()
        if not active_acc:
            return

        ai_settings = self.ai_engine.get_settings()
        max_trades = ai_settings.get("max_open_trades", 5)

        current_open = [p for p in self.positions if p["account_id"] == active_acc["id"]]
        if len(current_open) >= max_trades:
            return

        whitelist = ai_settings.get("symbols_whitelist", ["EURUSD", "XAUUSD", "BTCUSDT", "NVDA", "AAPL"])
        import random
        symbols_to_check = list(whitelist)
        random.shuffle(symbols_to_check)

        for sym in symbols_to_check:
            if any(p["symbol"] == sym for p in current_open):
                continue

            cfg = self.market_feed.get_symbol_info(sym)
            candles = self.market_feed.get_candles(sym, "15m")
            h1_candles = self.market_feed.get_candles(sym, "1h")
            p_info = self.market_feed.prices.get(sym)
            if not p_info:
                continue

            signal = self.ai_engine.evaluate_market(sym, cfg, candles, p_info, h1_candles=h1_candles)
            if signal:
                # Kalkulasi besaran lot cerdas AI berdasarkan akun riil aktif
                ai_lot = self.ai_engine.calculate_lot_size(
                    symbol=sym,
                    symbol_cfg=cfg,
                    account=active_acc,
                    entry_price=signal["price"],
                    sl_price=signal["sl"],
                    confidence=signal.get("confidence", 75.0),
                    is_ai=True
                )

                reason_str = f"[{signal['strategy']}] Lot: {ai_lot} | " + " | ".join(signal["reasoning"][:2])
                res = self.open_position(
                    account_id=active_acc["id"],
                    symbol=sym,
                    direction=signal["direction"],
                    lot=ai_lot,
                    sl=signal["sl"],
                    tp=signal["tp"],
                    strategy=signal["strategy"],
                    is_ai=True,
                    reasoning=reason_str
                )
                if res.get("success"):
                    self.log_event(
                        f"🤖 Robot AI mengeksekusi {signal['direction']} {sym} (Lot: {ai_lot}, Confidence: {signal['confidence']}%)",
                        level="info",
                        symbol=sym
                    )
                break


    def get_performance_metrics(self, account_id: str):
        trades = [h for h in self.history if h["account_id"] == account_id]
        total_trades = len(trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "equity_curve": []
            }

        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        total_pnl = sum(t["pnl"] for t in trades)
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))

        win_rate = round((len(wins) / total_trades) * 100, 1)
        profit_factor = round(gross_profit / max(gross_loss, 1.0), 2)

        acc = None
        for a in self.account_mgr.get_all():
            if a["id"] == account_id:
                acc = a
                break
        
        initial_bal = acc.get("initial_balance", 10000.0) if acc else 10000.0
        equity_points = [{"t": "Start", "v": initial_bal}]
        running_bal = initial_bal
        peak = initial_bal
        max_dd = 0.0

        for idx, t in enumerate(reversed(trades)):
            running_bal += t["pnl"]
            if running_bal > peak:
                peak = running_bal
            dd = ((peak - running_bal) / peak) * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
            equity_points.append({"t": f"T{idx+1}", "v": round(running_bal, 2)})

        return {
            "total_trades": total_trades,
            "win_trades": len(wins),
            "loss_trades": len(losses),
            "win_rate": win_rate,
            "total_pnl": round(total_pnl, 2),
            "profit_factor": profit_factor,
            "max_drawdown": round(max_dd, 1),
            "equity_curve": equity_points
        }

    def get_circuit_breaker_status(self, account_id: str = None) -> Dict[str, Any]:
        active_acc = None
        if account_id:
            for a in self.account_mgr.get_all():
                if a["id"] == account_id:
                    active_acc = a
                    break
        if not active_acc:
            active_acc = self.account_mgr.get_active()

        daily_loss_pct = 0.0
        start_bal = 0.0
        if active_acc:
            acc_id = active_acc["id"]
            start_bal = self.daily_start_balances.get(acc_id, active_acc.get("balance", 0.0))
            curr_equity = active_acc.get("equity", start_bal)
            if start_bal > 0:
                daily_loss = start_bal - curr_equity
                daily_loss_pct = max(0.0, round((daily_loss / start_bal) * 100, 2))

        return {
            "success": True,
            "tripped": self.circuit_breaker_tripped,
            "reason": self.circuit_breaker_reason,
            "daily_loss_pct": daily_loss_pct,
            "daily_start_balance": round(start_bal, 2),
            "limit_pct": self.ai_engine.get_settings().get("daily_loss_limit_pct", 5.0)
        }

    def trigger_kill_switch(self) -> Dict[str, Any]:
        """Tombol Darurat: Segera likuidasi seluruh posisi terbuka & matikan Robot AI"""
        closed_count = self.close_all()
        self.circuit_breaker_tripped = True
        self.circuit_breaker_reason = "Emergency Kill-Switch diaktifkan secara manual oleh pengguna"
        
        # Nonaktifkan AI Robot
        self.ai_engine.settings["mode"] = "paused"
        
        self.log_event(
            f"🛑 EMERGENCY KILL-SWITCH: Menutup paksa {closed_count} posisi trading & menonaktifkan Robot AI segera!",
            level="error"
        )
        status = self.get_circuit_breaker_status()
        return {
            "success": True,
            "message": f"Kill-Switch berhasil! {closed_count} posisi ditutup & Robot AI dihentikan.",
            "closed_count": closed_count,
            "status": {
                "circuit_breaker": status,
                "open_positions": self.positions,
                "ai_mode": self.ai_engine.settings["mode"]
            }
        }

    def reset_circuit_breaker(self) -> Dict[str, Any]:
        """Membuka kunci Circuit Breaker secara manual setelah evaluasi risiko"""
        self.circuit_breaker_tripped = False
        self.circuit_breaker_reason = ""
        active_acc = self.account_mgr.get_active()
        if active_acc:
            self.daily_start_balances[active_acc["id"]] = active_acc["balance"]

        self.log_event("🛡️ Circuit Breaker telah di-reset manual. Proteksi risiko siap kembali.", level="info")
        status = self.get_circuit_breaker_status()
        return {
            "success": True,
            "message": "Circuit Breaker berhasil di-reset.",
            "circuit_breaker": status
        }

