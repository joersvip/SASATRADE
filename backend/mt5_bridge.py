import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger("mt5_bridge")

class MT5Bridge:
    def __init__(self):
        self.is_available = False
        self.connected = False
        self.account_info = None
        self.terminal_info = None
        self._check_library()

    def _check_library(self):
        try:
            import importlib
            mt5 = importlib.import_module("MetaTrader5")
            self.mt5 = mt5
            self.is_available = True
            logger.info("Library MetaTrader5 terdeteksi dan siap digunakan.")
        except (ImportError, ModuleNotFoundError, Exception):
            self.mt5 = None
            self.is_available = False
            logger.warning("Library MetaTrader5 belum terpasang.")


    def auto_connect_active_terminal(self) -> Dict[str, Any]:
        """
        Mendeteksi terminal MetaTrader 5 yang sedang aktif dan menggunakan
        sesi akun broker yang sudah login (misalnya Exness di terminal).
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "Library MetaTrader5 belum terpasang di sistem Python."
            }

        try:
            # Inisialisasi terminal default
            if not self.mt5.initialize():
                err = self.mt5.last_error()
                return {
                    "success": False,
                    "error": f"Gagal menginisialisasi terminal MT5: {err}"
                }

            term_info = self.mt5.terminal_info()
            self.terminal_info = term_info._asdict() if term_info else {}

            acc = self.mt5.account_info()
            if acc and getattr(acc, "login", 0) > 0:
                self.connected = True
                self.account_info = acc._asdict()
                logger.info(
                    f"Berhasil auto-sinkron ke MT5 aktif: Login={acc.login}, "
                    f"Server={acc.server}, Saldo={acc.balance} {acc.currency}"
                )
                return {
                    "success": True,
                    "account_info": self.account_info,
                    "terminal_info": self.terminal_info
                }
            else:
                return {
                    "success": False,
                    "error": "Terminal MT5 terdeteksi tetapi belum ada akun yang login di terminal."
                }
        except Exception as e:
            logger.error(f"Error pada auto_connect_active_terminal: {e}")
            return {"success": False, "error": str(e)}

    def connect(self, login: int, password: str, server: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Login ke akun MT5 broker tertentu menggunakan kredensial."""
        if not self.is_available:
            return {
                "success": False,
                "error": "Library MetaTrader5 belum terpasang di sistem Python."
            }

        try:
            init_kwargs = {}
            if path:
                init_kwargs["path"] = path

            if not self.mt5.initialize(**init_kwargs):
                err = self.mt5.last_error()
                return {
                    "success": False,
                    "error": f"Gagal menginisialisasi terminal MT5: {err}"
                }

            authorized = self.mt5.login(int(login), password=password, server=server)
            if authorized:
                self.connected = True
                acc = self.mt5.account_info()
                self.account_info = acc._asdict() if acc else {}
                term_info = self.mt5.terminal_info()
                self.terminal_info = term_info._asdict() if term_info else {}
                logger.info(f"Berhasil login ke MT5: {login} @ {server}")
                return {
                    "success": True,
                    "account_info": self.account_info,
                    "terminal_info": self.terminal_info
                }
            else:
                err = self.mt5.last_error()
                self.connected = False
                return {
                    "success": False,
                    "error": f"Login MT5 ditolak oleh server '{server}'. Kode error: {err}"
                }
        except Exception as e:
            self.connected = False
            return {"success": False, "error": str(e)}

    def disconnect(self):
        if self.is_available and self.connected:
            try:
                self.mt5.shutdown()
            except Exception:
                pass
            self.connected = False
            self.account_info = None

    def get_real_account_metrics(self) -> Optional[Dict[str, Any]]:
        """Mengambil metrik akun real-time langsung dari MT5."""
        if not self.is_available or not self.connected:
            return None
        try:
            acc = self.mt5.account_info()
            if acc:
                d = acc._asdict()
                self.account_info = d
                return {
                    "balance": float(d.get("balance", 0.0)),
                    "equity": float(d.get("equity", 0.0)),
                    "margin": float(d.get("margin", 0.0)),
                    "free_margin": float(d.get("margin_free", 0.0)),
                    "margin_level": float(d.get("margin_level", 0.0)),
                    "profit": float(d.get("profit", 0.0)),
                    "leverage": int(d.get("leverage", 100)),
                    "currency": d.get("currency", "USD"),
                    "company": d.get("company", "Exness"),
                    "server": d.get("server", ""),
                    "login": d.get("login", 0),
                    "trade_allowed": bool(d.get("trade_allowed", True)),
                    "trade_expert": bool(d.get("trade_expert", True))
                }
        except Exception as e:
            logger.error(f"Error fetching MT5 account metrics: {e}")
        return None

    def resolve_symbol(self, symbol: str) -> str:
        """
        Mencocokkan simbol standar (misal EURUSD) dengan simbol broker
        (misal EURUSDm di Exness Standard, EURUSD.r, dsb.)
        """
        if not self.is_available or not self.connected:
            return symbol

        try:
            # 1. Cek apakah simbol persis ada
            if self.mt5.symbol_select(symbol, True):
                return symbol

            # 2. Cek variasi suffix umum Exness dan broker lain: 'm', 'c', '.r', '_i'
            variations = [f"{symbol}m", f"{symbol}c", f"{symbol}.r", f"{symbol}_i", f"{symbol}#"]
            for var in variations:
                if self.mt5.symbol_select(var, True):
                    logger.info(f"Simbol {symbol} disesuaikan ke format broker: {var}")
                    return var

            # 3. Cari dari daftar simbol broker yang mengandung nama simbol
            symbols = self.mt5.symbols_get()
            if symbols:
                target_lower = symbol.lower()
                exact_starts = [s.name for s in symbols if s.name.lower().startswith(target_lower)]
                if exact_starts:
                    chosen = exact_starts[0]
                    self.mt5.symbol_select(chosen, True)
                    return chosen

                contains = [s.name for s in symbols if target_lower in s.name.lower()]
                if contains:
                    chosen = contains[0]
                    self.mt5.symbol_select(chosen, True)
                    return chosen
        except Exception as e:
            logger.warning(f"Error saat mencari simbol {symbol}: {e}")

        return symbol

    def get_real_open_positions(self) -> List[Dict[str, Any]]:
        """Mengambil seluruh posisi terbuka riil langsung dari broker MT5."""
        if not self.is_available or not self.connected:
            return []

        try:
            positions = self.mt5.positions_get()
            if positions is None:
                return []

            results = []
            for pos in positions:
                is_buy = (pos.type == self.mt5.ORDER_TYPE_BUY)
                sym = pos.symbol
                clean_sym = sym
                if sym.endswith("m") and len(sym) > 3:
                    clean_sym = sym[:-1]
                elif sym.endswith(".r") or sym.endswith("_i"):
                    clean_sym = sym[:-2]

                pnl = round(float(pos.profit), 2)
                entry = float(pos.price_open)
                curr = float(pos.price_current)

                results.append({
                    "id": f"mt5-{pos.ticket}",
                    "ticket": pos.ticket,
                    "symbol": sym,
                    "clean_symbol": clean_sym,
                    "direction": "BUY" if is_buy else "SELL",
                    "lot": float(pos.volume),
                    "entry_price": entry,
                    "current_price": curr,
                    "sl": float(pos.sl) if pos.sl else 0.0,
                    "tp": float(pos.tp) if pos.tp else 0.0,
                    "pnl": pnl,
                    "swap": float(pos.swap),
                    "open_time": int(pos.time),
                    "comment": pos.comment or "Exness MT5 Position",
                    "mode": "real",
                    "is_broker_synced": True
                })
            return results
        except Exception as e:
            logger.error(f"Error fetching MT5 open positions: {e}")
            return []

    def get_history_deals(self, days: int = 7) -> List[Dict[str, Any]]:
        """Mengambil riwayat transaksi tertutup dari broker MT5."""
        if not self.is_available or not self.connected:
            return []

        try:
            from_time = datetime.now() - timedelta(days=days)
            to_time = datetime.now() + timedelta(days=1)
            deals = self.mt5.history_deals_get(from_time, to_time)
            if not deals:
                return []

            results = []
            for deal in reversed(deals):
                if deal.entry == 1 or deal.profit != 0.0:
                    is_buy = (deal.type == self.mt5.ORDER_TYPE_BUY)
                    results.append({
                        "id": f"deal-{deal.ticket}",
                        "ticket": deal.ticket,
                        "order": deal.order,
                        "symbol": deal.symbol,
                        "direction": "BUY" if is_buy else "SELL",
                        "lot": float(deal.volume),
                        "price": float(deal.price),
                        "profit": round(float(deal.profit), 2),
                        "commission": float(deal.commission),
                        "swap": float(deal.swap),
                        "time": int(deal.time),
                        "comment": deal.comment or "Exness Trade History"
                    })
            return results
        except Exception as e:
            logger.error(f"Error fetching MT5 history deals: {e}")
            return []

    def send_order(self, symbol: str, direction: str, volume: float, sl: float = 0.0, tp: float = 0.0, comment: str = "ApexAI Real") -> Dict[str, Any]:
        """Kirim order riil langsung ke pasar via MetaTrader 5 dengan auto-symbol mapping."""
        if not self.is_available or not self.connected:
            return {"success": False, "error": "Terminal MT5 belum terhubung ke broker"}

        try:
            broker_symbol = self.resolve_symbol(symbol)
            symbol_info = self.mt5.symbol_info(broker_symbol)
            if not symbol_info:
                return {"success": False, "error": f"Simbol {symbol} (broker: {broker_symbol}) tidak ditemukan di broker MT5"}

            if not symbol_info.visible:
                self.mt5.symbol_select(broker_symbol, True)

            tick = self.mt5.symbol_info_tick(broker_symbol)
            if not tick:
                return {"success": False, "error": f"Tidak ada data tick pasar untuk {broker_symbol}"}

            is_buy = direction.upper() == "BUY"
            price = tick.ask if is_buy else tick.bid
            order_type = self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL

            filling = self.mt5.ORDER_FILLING_IOC
            if hasattr(symbol_info, "filling_mode"):
                if symbol_info.filling_mode & 1:
                    filling = self.mt5.ORDER_FILLING_FOK
                elif symbol_info.filling_mode & 2:
                    filling = self.mt5.ORDER_FILLING_IOC
                else:
                    filling = self.mt5.ORDER_FILLING_RETURN

            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": broker_symbol,
                "volume": float(volume),
                "type": order_type,
                "price": float(price),
                "sl": float(sl) if sl else 0.0,
                "tp": float(tp) if tp else 0.0,
                "deviation": 30,
                "magic": 998877,
                "comment": comment,
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            result = self.mt5.order_send(request)
            if result is None:
                return {"success": False, "error": f"order_send mengembalikan None: {self.mt5.last_error()}"}

            if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                return {
                    "success": False,
                    "error": f"Eksekusi ditolak broker: retcode={result.retcode} ({result.comment})"
                }

            return {
                "success": True,
                "ticket": result.order,
                "deal": result.deal,
                "price": result.price,
                "volume": result.volume,
                "symbol": broker_symbol
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_order(self, ticket: int, symbol: str, direction: str, volume: float) -> Dict[str, Any]:
        """Tutup posisi riil di MT5."""
        if not self.is_available or not self.connected:
            return {"success": False, "error": "MT5 tidak terhubung"}

        try:
            broker_symbol = self.resolve_symbol(symbol)
            tick = self.mt5.symbol_info_tick(broker_symbol)
            if not tick:
                return {"success": False, "error": f"Tick pasar {broker_symbol} tidak tersedia"}

            is_buy = direction.upper() == "BUY"
            close_price = tick.bid if is_buy else tick.ask
            close_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY

            symbol_info = self.mt5.symbol_info(broker_symbol)
            filling = self.mt5.ORDER_FILLING_IOC
            if symbol_info and hasattr(symbol_info, "filling_mode"):
                if symbol_info.filling_mode & 1:
                    filling = self.mt5.ORDER_FILLING_FOK
                elif symbol_info.filling_mode & 2:
                    filling = self.mt5.ORDER_FILLING_IOC
                else:
                    filling = self.mt5.ORDER_FILLING_RETURN

            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": broker_symbol,
                "volume": float(volume),
                "type": close_type,
                "position": int(ticket),
                "price": float(close_price),
                "deviation": 30,
                "magic": 998877,
                "comment": "ApexAI Close",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            result = self.mt5.order_send(request)
            if result is None:
                return {"success": False, "error": f"Close order gagal: {self.mt5.last_error()}"}

            if result.retcode != self.mt5.TRADE_RETCODE_DONE:
                return {"success": False, "error": f"Gagal close MT5: retcode={result.retcode} ({result.comment})"}

            return {"success": True, "deal": result.deal, "price": result.price}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Status menyeluruh koneksi broker MT5."""
        term_connected = False
        if self.is_available and self.connected:
            try:
                t = self.mt5.terminal_info()
                term_connected = getattr(t, "connected", False) if t else False
            except Exception:
                term_connected = False

        return {
            "is_available": self.is_available,
            "connected": self.connected,
            "terminal_connected": term_connected,
            "account_info": self.account_info,
            "terminal_info": self.terminal_info
        }

