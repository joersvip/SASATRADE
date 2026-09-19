import os
import asyncio
import json
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.account_manager import AccountManager
from backend.market_feed import MarketFeedManager
from backend.ai_engine import AIEngine
from backend.trading_engine import TradingEngine
from backend.mt5_bridge import MT5Bridge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trading_server")

# Inisialisasi Modul
account_mgr = AccountManager()
market_feed = MarketFeedManager()
ai_engine = AIEngine()
mt5_bridge = MT5Bridge()
trading_engine = TradingEngine(account_mgr, market_feed, ai_engine, mt5_bridge)

app = FastAPI(title="AI Auto Trading Robot & Multi-Market Dashboard")

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/js/") or path.startswith("/css/") or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
os.makedirs(PUBLIC_DIR, exist_ok=True)

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_conns = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead_conns.append(conn)
        for dead in dead_conns:
            self.disconnect(dead)

ws_manager = ConnectionManager()

# Background Loop: Tick Engine & Real-time Broadcast
async def background_trading_loop():
    logger.info("Background Trading Engine Loop Started...")
    while True:
        try:
            trading_engine.tick_cycle()
            
            # Broadcast latest tick & positions state to connected clients
            if ws_manager.active_connections:
                active_acc = account_mgr.get_active()
                acc_id = active_acc["id"] if active_acc else None
                
                open_pos = [p for p in trading_engine.positions if not acc_id or p["account_id"] == acc_id]
                perf = trading_engine.get_performance_metrics(acc_id) if acc_id else {}
                breaker_status = trading_engine.get_circuit_breaker_status(acc_id)

                data = {
                    "type": "tick_update",
                    "prices": market_feed.get_market_overview(),
                    "active_account": active_acc,
                    "open_positions": open_pos,
                    "performance": perf,
                    "circuit_breaker": breaker_status,
                    "ai_learning": ai_engine.get_learning_stats(),
                    "recent_logs": trading_engine.logs[:10],
                    "recent_signals": ai_engine.recent_signals[:5]
                }
                await ws_manager.broadcast(data)
        except Exception as e:
            logger.error(f"Error in background trading loop: {e}")

        await asyncio.sleep(0.5)

@app.on_event("startup")
async def startup_event():
    # Auto-reconnect / auto-sync ke terminal MT5 Exness saat server dimulai
    try:
        active_acc = account_mgr.get_active()
        if active_acc and active_acc.get("type") == "mt5":
            creds = active_acc.get("credentials", {})
            if creds.get("login") and creds.get("password") and creds.get("server"):
                res = mt5_bridge.connect(int(creds["login"]), creds["password"], creds["server"])
                if res.get("success"):
                    logger.info(f"Auto-reconnected ke akun MT5 tersimpan: {creds['login']}")
                    metrics = mt5_bridge.get_real_account_metrics()
                    if metrics:
                        account_mgr.sync_mt5_account(metrics, creds)
                else:
                    logger.warning(f"Gagal reconnect akun MT5 tersimpan: {res.get('error')}")
            else:
                auto_res = mt5_bridge.auto_connect_active_terminal()
                if auto_res.get("success"):
                    metrics = mt5_bridge.get_real_account_metrics()
                    if metrics:
                        account_mgr.sync_mt5_account(metrics)
                        logger.info("Auto-sync ke terminal MT5 aktif berhasil saat startup.")
        else:
            # Periksa apakah ada terminal MT5 aktif
            auto_res = mt5_bridge.auto_connect_active_terminal()
            if auto_res.get("success"):
                logger.info("Terminal MT5 aktif terdeteksi saat startup server.")
    except Exception as e:
        logger.warning(f"MT5 startup check error: {e}")

    asyncio.create_task(background_trading_loop())
    asyncio.create_task(market_feed.run_realtime_crypto_ws())

# REST API Endpoints

@app.get("/api/state")
def get_full_state():
    active_acc = account_mgr.get_active()
    acc_id = active_acc["id"] if active_acc else None
    
    return {
        "active_account": active_acc,
        "all_accounts": account_mgr.get_all(),
        "markets": market_feed.get_market_overview(),
        "open_positions": [p for p in trading_engine.positions if not acc_id or p["account_id"] == acc_id],
        "history": [h for h in trading_engine.history if not acc_id or h["account_id"] == acc_id][:40],
        "ai_settings": ai_engine.get_settings(),
        "ai_strategies": ai_engine.strategies,
        "ai_api_config": ai_engine.get_api_config(),
        "ai_learning": ai_engine.get_learning_stats(),
        "recent_signals": ai_engine.recent_signals,
        "logs": trading_engine.logs,
        "performance": trading_engine.get_performance_metrics(acc_id) if acc_id else {},
        "circuit_breaker": trading_engine.get_circuit_breaker_status(acc_id),
        "mt5_status": mt5_bridge.get_status(),
        "mt5_metrics": mt5_bridge.get_real_account_metrics() if mt5_bridge.connected else None
    }


@app.get("/api/markets")
def get_markets():
    return market_feed.get_market_overview()

@app.get("/api/candles")
def get_candles(symbol: str = "EURUSD", timeframe: str = "15m"):
    candles = market_feed.get_candles(symbol, timeframe)
    cfg = market_feed.get_symbol_info(symbol)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "info": cfg,
        "candles": candles
    }

# Account Management
class SwitchAccountModel(BaseModel):
    account_id: str

@app.post("/api/accounts/switch")
def switch_account(body: SwitchAccountModel):
    success = account_mgr.set_active(body.account_id)
    if not success:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    trading_engine.log_event(f"Beralih ke akun: {account_mgr.get_active()['name']}", level="info")
    return {"success": True, "active_account": account_mgr.get_active()}

class CreateAccountModel(BaseModel):
    name: str
    type: str = "demo"
    initial_balance: float = 10000.0
    leverage: int = 100
    currency: str = "USD"
    credentials: Optional[Dict[str, Any]] = None

@app.post("/api/accounts/create")
def create_account(body: CreateAccountModel):
    acc = account_mgr.create(
        name=body.name,
        acc_type=body.type,
        initial_balance=body.initial_balance,
        leverage=body.leverage,
        currency=body.currency,
        credentials=body.credentials
    )
    account_mgr.set_active(acc["id"])
    trading_engine.log_event(f"Akun baru dibuat: {acc['name']} ({acc['currency']} {acc['balance']:,.2f})", level="success")
    return {"success": True, "account": acc}

class ConnectRealAccountModel(BaseModel):
    platform: str  # "mt5" or "crypto"
    account_name: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    server: Optional[str] = None
    broker: Optional[str] = None
    exchange: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    market_type: Optional[str] = "futures"
    initial_balance: Optional[float] = 1000.0
    leverage: Optional[int] = 100
    currency: Optional[str] = "USD"

@app.post("/api/mt5/auto-sync")
def auto_sync_mt5_terminal():
    """Mendeteksi dan menyinkronkan langsung akun MT5/Exness yang aktif di terminal."""
    res = mt5_bridge.auto_connect_active_terminal()
    if not res.get("success"):
        raise HTTPException(
            status_code=400, 
            detail=res.get("error", "Gagal mendeteksi akun aktif di terminal MT5.")
        )
    
    metrics = mt5_bridge.get_real_account_metrics()
    if not metrics:
        raise HTTPException(status_code=400, detail="Gagal mengambil metrik akun dari MT5.")

    acc = account_mgr.sync_mt5_account(metrics)
    trading_engine.log_event(
        f"⚡ [AUTO-SYNC EXNESS] Akun MT5 {metrics.get('login')} ({metrics.get('company')}) tersinkronisasi! Saldo: {metrics.get('currency')} {metrics.get('balance'):,.2f}",
        level="success"
    )
    trading_engine._sync_mt5_live_positions(acc["id"])

    return {
        "success": True, 
        "account": acc, 
        "metrics": metrics,
        "message": f"Akun {acc['name']} ({metrics.get('company')}) berhasil disinkronkan dari MetaTrader 5."
    }

@app.post("/api/auth/connect-real")
def connect_real_account(body: ConnectRealAccountModel):
    name = body.account_name or (f"MT5 Real ({body.broker or 'Broker'})" if body.platform == "mt5" else f"{body.exchange or 'Crypto'} Real API")
    
    if body.platform == "mt5":
        creds = {
            "broker": body.broker or "Exness",
            "server": body.server or "",
            "login": body.login or "",
            "password": body.password or ""
        }
        # Validasi kredensial login MT5
        if not body.login or not body.password or not body.server:
            raise HTTPException(status_code=400, detail="Login, Password, dan Server MT5 wajib diisi.")
        
        try:
            login_int = int(body.login)
        except ValueError:
            raise HTTPException(status_code=400, detail="Nomor Akun (Login) MT5 harus berupa angka.")

        mt5_res = mt5_bridge.connect(login_int, body.password, body.server)
        if not mt5_res.get("success"):
            raise HTTPException(
                status_code=400, 
                detail=mt5_res.get("error", f"Login MT5 gagal. Pastikan nomor login, password, dan server '{body.server}' benar.")
            )

        metrics = mt5_bridge.get_real_account_metrics()
        if not metrics:
            raise HTTPException(status_code=400, detail="Gagal mengambil metrik akun setelah login MT5.")

        acc = account_mgr.sync_mt5_account(metrics, credentials=creds)
        trading_engine._sync_mt5_live_positions(acc["id"])

        trading_engine.log_event(
            f"🔐 [AKUN REAL MT5] Berhasil terhubung & diaktifkan: {acc['name']} ({metrics.get('company')}) - Saldo: {metrics.get('currency')} {metrics.get('balance'):,.2f}",
            level="success"
        )
        return {"success": True, "account": acc, "metrics": metrics, "bridge_info": mt5_res}

    else:
        creds = {
            "exchange": body.exchange or "Binance Futures",
            "apiKey": body.api_key or "",
            "secret": body.api_secret or "",
            "market_type": body.market_type or "futures"
        }
        acc = account_mgr.connect_real_account(
            platform=body.platform,
            name=name,
            credentials=creds,
            initial_balance=body.initial_balance or 1000.0,
            leverage=body.leverage or 100,
            currency=body.currency or "USDT"
        )
        trading_engine.log_event(
            f"🔐 [AKUN REAL CRYPTO] Berhasil terhubung: {acc['name']}",
            level="warning"
        )
        return {"success": True, "account": acc}


class ResetAccountModel(BaseModel):
    account_id: str
    new_balance: Optional[float] = None

@app.post("/api/accounts/reset")
def reset_account(body: ResetAccountModel):
    acc = account_mgr.reset_balance(body.account_id, body.new_balance)
    if not acc:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    # Bersihkan posisi akun yang di-reset
    trading_engine.positions = [p for p in trading_engine.positions if p["account_id"] != body.account_id]
    trading_engine._save_trades()
    trading_engine.log_event(f"Saldo {acc['name']} direset menjadi ${acc['balance']:,.2f}", level="info")
    return {"success": True, "account": acc}

class DeleteAccountModel(BaseModel):
    account_id: str

@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str):
    acc_to_del = next((a for a in account_mgr.get_all() if a["id"] == account_id), None)
    acc_name = acc_to_del["name"] if acc_to_del else account_id

    success = account_mgr.delete(account_id)
    if not success:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus akun terakhir atau akun tidak ditemukan")

    # Bersihkan posisi open akun yang dihapus
    trading_engine.positions = [p for p in trading_engine.positions if p.get("account_id") != account_id]
    trading_engine._save_trades()

    active_acc = account_mgr.get_active()
    trading_engine.log_event(f"🗑️ Akun '{acc_name}' telah dihapus. Akun aktif saat ini: {active_acc['name'] if active_acc else '-'}", level="warning")
    return {"success": True, "accounts": account_mgr.get_all(), "active_account": active_acc}

@app.post("/api/accounts/delete")
def delete_account_post(body: DeleteAccountModel):
    return delete_account(body.account_id)

# Trading Operations
class OpenOrderModel(BaseModel):
    symbol: str
    direction: str
    lot: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    strategy: Optional[str] = "Manual Trade"

@app.post("/api/order/open")
def open_order(body: OpenOrderModel):
    active_acc = account_mgr.get_active()
    if not active_acc:
        raise HTTPException(status_code=400, detail="Tidak ada akun aktif")
    
    result = trading_engine.open_position(
        account_id=active_acc["id"],
        symbol=body.symbol,
        direction=body.direction.upper(),
        lot=body.lot,
        sl=body.sl,
        tp=body.tp,
        strategy=body.strategy,
        is_ai=False
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Gagal membuka order"))
    return result

class CloseOrderModel(BaseModel):
    position_id: str

@app.post("/api/order/close")
def close_order(body: CloseOrderModel):
    result = trading_engine.close_position(body.position_id, reason="Manual User Close")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Gagal menutup order"))
    return result

@app.post("/api/order/close/{position_id}")
def close_order_path(position_id: str):
    result = trading_engine.close_position(position_id, reason="Manual User Close")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Gagal menutup order"))
    return result

@app.post("/api/order/close-all")
def close_all_orders():
    active_acc = account_mgr.get_active()
    acc_id = active_acc["id"] if active_acc else None
    count = trading_engine.close_all(acc_id)
    return {"success": True, "closed_count": count}

class ModifyOrderModel(BaseModel):
    position_id: str
    sl: float
    tp: float

@app.post("/api/order/modify")
def modify_order(body: ModifyOrderModel):
    result = trading_engine.modify_position(body.position_id, body.sl, body.tp)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Gagal mengubah order"))
    return result

# AI Bot Controls
@app.get("/api/ai/settings")
def get_ai_settings():
    return {
        "settings": ai_engine.get_settings(),
        "strategies": ai_engine.strategies
    }

class UpdateAISettingsModel(BaseModel):
    mode: Optional[str] = None
    active_strategy: Optional[str] = None
    confidence_threshold: Optional[int] = None
    risk_per_trade_pct: Optional[float] = None
    max_open_trades: Optional[int] = None
    trailing_stop_enabled: Optional[bool] = None

@app.post("/api/ai/settings")
def update_ai_settings(body: UpdateAISettingsModel):
    data = body.dict(exclude_none=True)
    updated = ai_engine.update_settings(data)
    trading_engine.log_event(f"Pengaturan AI Robot diperbarui: Mode={updated.get('mode')}, Strategi={updated.get('active_strategy')}", level="info")
    return {"success": True, "settings": updated}

@app.post("/api/ai/toggle")
def toggle_ai():
    cur = ai_engine.settings.get("mode", "off")
    new_mode = "off" if cur == "auto" else "auto"
    ai_engine.settings["mode"] = new_mode
    status_str = "DIAKTIFKAN (Auto Execution)" if new_mode == "auto" else "DINONAKTIFKAN (Pause)"
    trading_engine.log_event(f"Robot Trading AI {status_str}", level="warning" if new_mode == "auto" else "info")
    return {"success": True, "mode": new_mode}

@app.post("/api/ai/scan-now")
def trigger_ai_scan():
    trading_engine._run_ai_auto_scan()
    return {"success": True, "recent_signals": ai_engine.recent_signals[:5]}

# Backtest Laboratory Endpoint
class RunBacktestModel(BaseModel):
    symbol: str = "BTCUSDT"
    strategy: Optional[str] = None
    strategy_id: Optional[str] = None
    timeframe: str = "15m"
    initial_balance: float = 10000.0
    risk_pct: float = 2.0
    confidence_threshold: int = 75

@app.post("/api/ai/backtest")
def run_backtest_endpoint(body: RunBacktestModel):
    strat = body.strategy_id or body.strategy or "scalping"
    candles = market_feed.get_candles(body.symbol, body.timeframe)
    symbol_cfg = market_feed.get_symbol_info(body.symbol)
    result = ai_engine.run_backtest(
        symbol=body.symbol,
        strategy_id=strat,
        candles=candles,
        symbol_cfg=symbol_cfg,
        initial_balance=body.initial_balance,
        risk_pct=body.risk_pct,
        confidence_threshold=body.confidence_threshold
    )
    return result

# Risk Protection & Kill-Switch Endpoints
@app.post("/api/risk/kill-switch")
def trigger_kill_switch_endpoint():
    return trading_engine.trigger_kill_switch()

@app.post("/api/risk/circuit-breaker/reset")
def reset_circuit_breaker_endpoint():
    return trading_engine.reset_circuit_breaker()

@app.get("/api/risk/circuit-breaker")
def get_circuit_breaker_endpoint():
    return {
        "success": True,
        "circuit_breaker": trading_engine.get_circuit_breaker_status()
    }

# Self-Learning AI Brain Endpoints
@app.get("/api/ai/learning-stats")
def get_ai_learning_stats_endpoint():
    return {
        "success": True,
        "learning": ai_engine.get_learning_stats()
    }

@app.post("/api/ai/learning/reset")
def reset_ai_learning_endpoint():
    return ai_engine.reset_learning_memory()

# AI API & URL Configuration Endpoints
@app.get("/api/ai/api-config")
def get_ai_api_config():
    return ai_engine.get_api_config()

class UpdateAIAPIConfigModel(BaseModel):
    provider: Optional[str] = "openai"
    api_url: Optional[str] = "https://api.openai.com/v1"
    api_key: Optional[str] = ""
    model: Optional[str] = "gpt-4o-mini"
    enabled: Optional[bool] = False

@app.post("/api/ai/api-config")
def update_ai_api_config(body: UpdateAIAPIConfigModel):
    data = body.dict(exclude_none=True)
    updated = ai_engine.update_api_config(data)
    trading_engine.log_event(
        f"Konfigurasi AI diperbarui: Provider={updated.get('provider')}, Model={updated.get('model')}, Aktif={updated.get('enabled')}",
        level="info"
    )
    return {"success": True, "config": updated}

class TestAIConnectionModel(BaseModel):
    provider: str
    api_url: str
    api_key: Optional[str] = ""
    model: str

@app.post("/api/ai/test-connection")
async def test_ai_connection(body: TestAIConnectionModel):
    result = await ai_engine.test_api_connection(
        provider=body.provider,
        api_url=body.api_url,
        api_key=body.api_key or "",
        model=body.model
    )
    return result

# WebSocket endpoint
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Listen to incoming ping or messages
            msg = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# Mount frontend files
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting ApexAI Trading Engine on {host}:{port}...")
    uvicorn.run("server:app", host=host, port=port, reload=False)
