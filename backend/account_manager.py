import json
import os
import time
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")

DEFAULT_ACCOUNTS = [
    {
        "id": "acc-demo-starter",
        "name": "Demo Sandbox (Uji Strategi)",
        "type": "demo",
        "mode": "demo",
        "currency": "USD",
        "balance": 10000.0,
        "initial_balance": 10000.0,
        "equity": 10000.0,
        "margin": 0.0,
        "free_margin": 10000.0,
        "margin_level": 0.0,
        "leverage": 100,
        "created_at": int(time.time()),
        "is_active": True,
        "status": "ready",
        "credentials": {
            "broker": "Production Engine Sandbox",
            "server": "Local-Environment"
        }
    }
]

class AccountManager:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.accounts = self._load()

    def _load(self):
        if not os.path.exists(ACCOUNTS_FILE):
            self._save_raw(DEFAULT_ACCOUNTS)
            return DEFAULT_ACCOUNTS
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_ACCOUNTS

    def _save_raw(self, accounts):
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)

    def save(self):
        self._save_raw(self.accounts)

    def get_all(self):
        return self.accounts

    def get_active(self):
        for acc in self.accounts:
            if acc.get("is_active"):
                return acc
        if self.accounts:
            self.accounts[0]["is_active"] = True
            self.save()
            return self.accounts[0]
        return None

    def set_active(self, account_id):
        found = False
        for acc in self.accounts:
            if acc["id"] == account_id:
                acc["is_active"] = True
                found = True
            else:
                acc["is_active"] = False
        if found:
            self.save()
            return True
        return False

    def create(self, name, acc_type="demo", initial_balance=10000.0, leverage=100, currency="USD", credentials=None):
        new_acc = {
            "id": f"acc-{uuid.uuid4().hex[:8]}",
            "name": name or f"Akun Baru ({acc_type.upper()})",
            "type": acc_type,
            "currency": currency,
            "balance": float(initial_balance),
            "initial_balance": float(initial_balance),
            "equity": float(initial_balance),
            "margin": 0.0,
            "free_margin": float(initial_balance),
            "margin_level": 0.0,
            "leverage": int(leverage),
            "created_at": int(time.time()),
            "is_active": False,
            "status": "connected" if acc_type == "demo" else "ready",
            "credentials": credentials or {}
        }
        self.accounts.append(new_acc)
        self.save()
        return new_acc

    def reset_balance(self, account_id, new_balance=None):
        for acc in self.accounts:
            if acc["id"] == account_id:
                target_bal = float(new_balance) if new_balance is not None else acc.get("initial_balance", 10000.0)
                acc["balance"] = target_bal
                acc["equity"] = target_bal
                acc["margin"] = 0.0
                acc["free_margin"] = target_bal
                acc["margin_level"] = 0.0
                self.save()
                return acc
        return None

    def delete(self, account_id):
        if len(self.accounts) <= 1:
            return False
        was_active = False
        new_list = []
        found = False
        for acc in self.accounts:
            if acc["id"] == account_id:
                found = True
                if acc.get("is_active"):
                    was_active = True
            else:
                new_list.append(acc)
        if not found:
            return False
        self.accounts = new_list
        if was_active and self.accounts:
            self.accounts[0]["is_active"] = True
        self.save()
        return True

    def update_metrics(self, account_id, balance=None, equity=None, margin=None, free_margin=None, margin_level=None):
        for acc in self.accounts:
            if acc["id"] == account_id:
                if balance is not None:
                    acc["balance"] = round(float(balance), 2)
                if equity is not None:
                    acc["equity"] = round(float(equity), 2)
                if margin is not None:
                    acc["margin"] = round(float(margin), 2)
                
                if free_margin is not None:
                    acc["free_margin"] = round(float(free_margin), 2)
                else:
                    acc["free_margin"] = round(acc["equity"] - acc.get("margin", 0.0), 2)

                if margin_level is not None:
                    acc["margin_level"] = round(float(margin_level), 2)
                else:
                    curr_margin = acc.get("margin", 0.0)
                    acc["margin_level"] = round((acc["equity"] / curr_margin * 100), 2) if curr_margin > 0 else 0.0
                
                self.save()
                return acc
        return None

    def sync_mt5_account(self, metrics: dict, credentials: dict = None):
        """Menyinkronkan akun aktif dengan metrik riil dari terminal MT5."""
        login_str = str(metrics.get("login", ""))
        server_str = metrics.get("server", "")
        broker_str = metrics.get("company", "Exness")
        currency = metrics.get("currency", "USD")
        balance = float(metrics.get("balance", 0.0))
        equity = float(metrics.get("equity", balance))
        margin = float(metrics.get("margin", 0.0))
        free_margin = float(metrics.get("free_margin", balance))
        margin_level = float(metrics.get("margin_level", 0.0))
        leverage = int(metrics.get("leverage", 100))

        # Cari akun mt5 yang cocok
        existing = None
        for acc in self.accounts:
            if acc.get("type") == "mt5":
                acc_creds = acc.get("credentials", {})
                if str(acc_creds.get("login", "")) == login_str:
                    existing = acc
                    break

        if not existing:
            # Cari akun mt5 apa saja
            for acc in self.accounts:
                if acc.get("type") == "mt5":
                    existing = acc
                    break

        name = f"Exness MT5 ({login_str})" if "exness" in broker_str.lower() else f"MT5 ({login_str} @ {server_str})"

        creds = credentials or {
            "broker": broker_str,
            "server": server_str,
            "login": login_str
        }

        if existing:
            existing["name"] = name
            existing["currency"] = currency
            existing["balance"] = balance
            existing["equity"] = equity
            existing["margin"] = margin
            existing["free_margin"] = free_margin
            existing["margin_level"] = margin_level
            existing["leverage"] = leverage
            existing["status"] = "connected"
            existing["mode"] = "real"
            existing["credentials"] = creds
            target_id = existing["id"]
        else:
            new_acc = {
                "id": f"acc-mt5-{uuid.uuid4().hex[:8]}",
                "name": name,
                "type": "mt5",
                "mode": "real",
                "currency": currency,
                "balance": balance,
                "initial_balance": balance,
                "equity": equity,
                "margin": margin,
                "free_margin": free_margin,
                "margin_level": margin_level,
                "leverage": leverage,
                "created_at": int(time.time()),
                "is_active": True,
                "status": "connected",
                "credentials": creds
            }
            self.accounts.append(new_acc)
            target_id = new_acc["id"]

        self.set_active(target_id)
        return self.get_active()

    def connect_real_account(self, platform: str, name: str, credentials: dict, initial_balance: float = 1000.0, leverage: int = 100, currency: str = "USD"):
        existing = None
        target_type = "mt5" if platform == "mt5" else "crypto_api"
        for acc in self.accounts:
            if acc.get("type") == target_type and acc.get("mode") == "real":
                existing = acc
                break

        if existing:
            existing["name"] = name
            existing["credentials"] = credentials
            existing["leverage"] = int(leverage)
            existing["currency"] = currency
            existing["balance"] = float(initial_balance)
            existing["equity"] = float(initial_balance)
            existing["free_margin"] = float(initial_balance)
            existing["status"] = "connected"
            target_id = existing["id"]
        else:
            new_acc = {
                "id": f"acc-real-{uuid.uuid4().hex[:8]}",
                "name": name,
                "type": target_type,
                "mode": "real",
                "currency": currency,
                "balance": float(initial_balance),
                "initial_balance": float(initial_balance),
                "equity": float(initial_balance),
                "margin": 0.0,
                "free_margin": float(initial_balance),
                "margin_level": 0.0,
                "leverage": int(leverage),
                "created_at": int(time.time()),
                "is_active": True,
                "status": "connected",
                "credentials": credentials
            }
            self.accounts.append(new_acc)
            target_id = new_acc["id"]

        self.set_active(target_id)
        return self.get_active()

