import os
import sqlite3
import json
import time
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("brain_db")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "apex_brain.db")
AI_MEMORY_JSON = os.path.join(DATA_DIR, "ai_memory.json")
AI_STRATEGIES_JSON = os.path.join(DATA_DIR, "ai_strategies.json")

class BrainDatabase:
    """
    SQLite Relational Knowledge Base & Evolutionary Memory Engine for ApexAI.
    Menyimpan profil kecerdasan AI, evolusi strategi trading, pola pasar yang dipelajari,
    jurnal refleksi belajar, dan checkpoint historis secara terstruktur dan terindeks.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_tables()
        self._migrate_from_json_if_needed()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Inisialisasi skema tabel relasional database AI Brain"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            # 1. Tabel Status Kognitif Otak AI (Brain State)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_brain_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    brain_level INTEGER NOT NULL DEFAULT 1,
                    experience_points INTEGER NOT NULL DEFAULT 0,
                    next_level_xp INTEGER NOT NULL DEFAULT 100,
                    total_trades_analyzed INTEGER NOT NULL DEFAULT 0,
                    profitable_trades INTEGER NOT NULL DEFAULT 0,
                    loss_trades INTEGER NOT NULL DEFAULT 0,
                    strategy_weights TEXT NOT NULL DEFAULT '{}',
                    regime_matrix TEXT NOT NULL DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. Tabel Strategi Hasil Evolusi AI (Strategy Registry)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_evolved_strategies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    creator TEXT NOT NULL,
                    description TEXT,
                    target_market TEXT,
                    min_rr REAL DEFAULT 2.0,
                    logic_type TEXT DEFAULT 'trend_confluence',
                    indicators TEXT NOT NULL DEFAULT '{}',
                    win_rate REAL DEFAULT 0.0,
                    profit_factor REAL DEFAULT 0.0,
                    max_drawdown REAL DEFAULT 0.0,
                    total_test_trades INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. Tabel Jurnal Refleksi Belajar Mandiri (Learning Journal)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_learning_journal (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    symbol TEXT,
                    strategy TEXT,
                    pnl REAL DEFAULT 0.0,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_type ON ai_learning_journal(type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_journal_symbol ON ai_learning_journal(symbol)")

            # 4. Tabel Pola Pasar yang Dipelajari (Learned Market Patterns)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_market_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    pattern_name TEXT NOT NULL,
                    regime TEXT DEFAULT 'all',
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0.0,
                    sample_notes TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 5. Tabel Checkpoint Evolusi Otak AI (Evolutionary Checkpoints)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_brain_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    brain_level INTEGER NOT NULL,
                    experience_points INTEGER NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def _migrate_from_json_if_needed(self):
        """Migrasi data awal dari file JSON yang ada ke database SQLite agar riwayat tidak hilang"""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM ai_brain_state WHERE id = 1")
                has_state = cur.fetchone()[0] > 0

                if not has_state and os.path.exists(AI_MEMORY_JSON):
                    with open(AI_MEMORY_JSON, "r", encoding="utf-8") as f:
                        mem = json.load(f)
                        cur.execute("""
                            INSERT INTO ai_brain_state (
                                id, brain_level, experience_points, next_level_xp,
                                total_trades_analyzed, profitable_trades, loss_trades,
                                strategy_weights, regime_matrix, updated_at
                            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (
                            mem.get("brain_level", 1),
                            mem.get("experience_points", 0),
                            mem.get("next_level_xp", 100),
                            mem.get("total_trades_analyzed", 0),
                            mem.get("profitable_trades", 0),
                            mem.get("loss_trades", 0),
                            json.dumps(mem.get("strategy_weights", {})),
                            json.dumps(mem.get("regime_matrix", {}))
                        ))

                        # Migrasi log insights
                        insights = mem.get("learned_insights", [])
                        for ins in insights:
                            ins_id = ins.get("id") or f"ins-{int(time.time()*1000)}"
                            cur.execute("""
                                INSERT OR IGNORE INTO ai_learning_journal (
                                    id, timestamp, type, symbol, strategy, pnl, message
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ins_id,
                                ins.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                                ins.get("type", "system"),
                                ins.get("symbol", ""),
                                ins.get("strategy", ""),
                                ins.get("pnl", 0.0),
                                ins.get("message", "")
                            ))

                # Migrasi strategi kustom
                if os.path.exists(AI_STRATEGIES_JSON):
                    with open(AI_STRATEGIES_JSON, "r", encoding="utf-8") as f:
                        strats = json.load(f)
                        for sid, s in strats.items():
                            bt = s.get("backtest_results", {})
                            cur.execute("""
                                INSERT OR REPLACE INTO ai_evolved_strategies (
                                    id, name, creator, description, target_market, min_rr,
                                    logic_type, indicators, win_rate, profit_factor, max_drawdown,
                                    total_test_trades, is_active, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                            """, (
                                sid,
                                s.get("name", sid),
                                s.get("creator", "AI Synthesizer"),
                                s.get("description", ""),
                                s.get("target_market", "XAUUSD"),
                                s.get("min_rr", 2.0),
                                s.get("logic_type", "trend_confluence"),
                                json.dumps(s.get("indicators", {})),
                                bt.get("win_rate", 0.0),
                                bt.get("profit_factor", 0.0),
                                bt.get("max_drawdown", 0.0),
                                bt.get("total_trades", 0),
                                s.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
                            ))

                conn.commit()
                logger.info("Migrasi data awal dari JSON ke SQLite Database selesai.")
        except Exception as e:
            logger.error(f"Error migrasi JSON ke SQLite: {e}")

    # =========================================================================
    # BRAIN STATE API
    # =========================================================================
    def get_brain_state(self) -> Dict[str, Any]:
        """Mengambil data status otak AI terkini dari database"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_brain_state WHERE id = 1")
            row = cur.fetchone()
            if not row:
                return {}
            
            # Ambil 30 jurnal catatan belajar terbaru
            cur.execute("SELECT * FROM ai_learning_journal ORDER BY created_at DESC, timestamp DESC LIMIT 30")
            insights = [dict(r) for r in cur.fetchall()]

            weights = json.loads(row["strategy_weights"]) if row["strategy_weights"] else {}
            regime = json.loads(row["regime_matrix"]) if row["regime_matrix"] else {}

            return {
                "brain_level": row["brain_level"],
                "experience_points": row["experience_points"],
                "next_level_xp": row["next_level_xp"],
                "total_trades_analyzed": row["total_trades_analyzed"],
                "profitable_trades": row["profitable_trades"],
                "loss_trades": row["loss_trades"],
                "strategy_weights": weights,
                "regime_matrix": regime,
                "learned_insights": insights,
                "updated_at": row["updated_at"]
            }

    def save_brain_state(self, mem: Dict[str, Any]):
        """Menyimpan status otak AI ke database SQLite dan sinkronisasi JSON backup"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ai_brain_state (
                    id, brain_level, experience_points, next_level_xp,
                    total_trades_analyzed, profitable_trades, loss_trades,
                    strategy_weights, regime_matrix, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    brain_level = excluded.brain_level,
                    experience_points = excluded.experience_points,
                    next_level_xp = excluded.next_level_xp,
                    total_trades_analyzed = excluded.total_trades_analyzed,
                    profitable_trades = excluded.profitable_trades,
                    loss_trades = excluded.loss_trades,
                    strategy_weights = excluded.strategy_weights,
                    regime_matrix = excluded.regime_matrix,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                mem.get("brain_level", 1),
                mem.get("experience_points", 0),
                mem.get("next_level_xp", 100),
                mem.get("total_trades_analyzed", 0),
                mem.get("profitable_trades", 0),
                mem.get("loss_trades", 0),
                json.dumps(mem.get("strategy_weights", {})),
                json.dumps(mem.get("regime_matrix", {}))
            ))

            # Simpan entri jurnal terbaru
            for ins in mem.get("learned_insights", [])[:30]:
                ins_id = ins.get("id") or f"ins-{int(time.time()*1000)}"
                cur.execute("""
                    INSERT OR IGNORE INTO ai_learning_journal (
                        id, timestamp, type, symbol, strategy, pnl, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    ins_id,
                    ins.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                    ins.get("type", "system"),
                    ins.get("symbol", ""),
                    ins.get("strategy", ""),
                    ins.get("pnl", 0.0),
                    ins.get("message", "")
                ))

            conn.commit()

        # Update file JSON untuk backward compatibility
        try:
            with open(AI_MEMORY_JSON, "w", encoding="utf-8") as f:
                json.dump(mem, f, indent=2)
        except Exception:
            pass

    def create_checkpoint(self, brain_level: int, xp: int, reason: str, snapshot: Dict[str, Any]):
        """Mencatat checkpoint evolusi otak AI"""
        chk_id = f"chk-{int(time.time()*1000)}"
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ai_brain_checkpoints (
                    checkpoint_id, brain_level, experience_points, trigger_reason, snapshot_json
                ) VALUES (?, ?, ?, ?, ?)
            """, (chk_id, brain_level, xp, reason, json.dumps(snapshot)))
            conn.commit()
        logger.info(f"AI Brain Checkpoint tersimpan: {chk_id} (Level {brain_level}, Trigger: {reason})")

    # =========================================================================
    # STRATEGY REGISTRY API
    # =========================================================================
    def save_evolved_strategy(self, strat: Dict[str, Any]):
        """Menyimpan strategi hasil evolusi mandiri ke database SQLite"""
        sid = strat["id"]
        bt = strat.get("backtest_results", {})
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO ai_evolved_strategies (
                    id, name, creator, description, target_market, min_rr,
                    logic_type, indicators, win_rate, profit_factor, max_drawdown,
                    total_test_trades, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
            """, (
                sid,
                strat.get("name", sid),
                strat.get("creator", "Autonomous AI Synthesizer"),
                strat.get("description", ""),
                strat.get("target_market", "XAUUSD"),
                strat.get("min_rr", 2.0),
                strat.get("logic_type", "trend_confluence"),
                json.dumps(strat.get("indicators", {})),
                bt.get("win_rate", 0.0),
                bt.get("profit_factor", 0.0),
                bt.get("max_drawdown", 0.0),
                bt.get("total_trades", 0),
                strat.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
            ))
            conn.commit()

        # Update JSON backup
        self.export_strategies_to_json()

    def get_all_evolved_strategies(self) -> Dict[str, Dict[str, Any]]:
        """Mengambil seluruh strategi hasil evolusi aktif dari database"""
        res = {}
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_evolved_strategies WHERE is_active = 1 ORDER BY created_at DESC")
            for row in cur.fetchall():
                ind = json.loads(row["indicators"]) if row["indicators"] else {}
                res[row["id"]] = {
                    "id": row["id"],
                    "name": row["name"],
                    "creator": row["creator"],
                    "description": row["description"],
                    "target_market": row["target_market"],
                    "min_rr": row["min_rr"],
                    "logic_type": row["logic_type"],
                    "indicators": ind,
                    "backtest_results": {
                        "win_rate": row["win_rate"],
                        "profit_factor": row["profit_factor"],
                        "max_drawdown": row["max_drawdown"],
                        "total_trades": row["total_test_trades"]
                    },
                    "created_at": str(row["created_at"])
                }
        return res

    def delete_evolved_strategy(self, strat_id: str) -> bool:
        """Menghapus/menonaktifkan strategi kustom dari database"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM ai_evolved_strategies WHERE id = ?", (strat_id,))
            affected = cur.rowcount
            conn.commit()
        self.export_strategies_to_json()
        return affected > 0

    def export_strategies_to_json(self):
        """Sinkronisasi dari database ke file JSON backup"""
        try:
            strats = self.get_all_evolved_strategies()
            with open(AI_STRATEGIES_JSON, "w", encoding="utf-8") as f:
                json.dump(strats, f, indent=2)
        except Exception as e:
            logger.warning(f"Gagal export strategies ke JSON: {e}")

    # =========================================================================
    # MARKET PATTERNS API
    # =========================================================================
    def record_pattern_outcome(self, symbol: str, pattern_name: str, success: bool, regime: str = "all", notes: str = ""):
        """Mencatat keberhasilan atau kegagalan pola teknikal yang dipelajari AI"""
        pat_id = f"{symbol}_{pattern_name.lower().replace(' ', '_')}"
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_market_patterns WHERE pattern_id = ?", (pat_id,))
            row = cur.fetchone()
            if row:
                s_count = row["success_count"] + (1 if success else 0)
                f_count = row["fail_count"] + (0 if success else 1)
                total = s_count + f_count
                wr = round((s_count / total) * 100, 1) if total > 0 else 0.0
                cur.execute("""
                    UPDATE ai_market_patterns SET
                        success_count = ?, fail_count = ?, win_rate = ?,
                        sample_notes = ?, last_seen = CURRENT_TIMESTAMP
                    WHERE pattern_id = ?
                """, (s_count, f_count, wr, notes or row["sample_notes"], pat_id))
            else:
                s_count = 1 if success else 0
                f_count = 0 if success else 1
                wr = 100.0 if success else 0.0
                cur.execute("""
                    INSERT INTO ai_market_patterns (
                        pattern_id, symbol, pattern_name, regime, success_count, fail_count, win_rate, sample_notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (pat_id, symbol, pattern_name, regime, s_count, f_count, wr, notes))
            conn.commit()

    # =========================================================================
    # DATABASE METRICS & STATS
    # =========================================================================
    def get_database_stats(self) -> Dict[str, Any]:
        """Mengambil metrik operasional database untuk dashboard UI"""
        file_size_kb = round(os.path.getsize(self.db_path) / 1024, 2) if os.path.exists(self.db_path) else 0.0
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            cur.execute("SELECT COUNT(*) FROM ai_evolved_strategies")
            strat_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM ai_learning_journal")
            journal_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM ai_market_patterns")
            pattern_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM ai_brain_checkpoints")
            checkpoint_count = cur.fetchone()[0]

            cur.execute("SELECT brain_level, experience_points, total_trades_analyzed FROM ai_brain_state WHERE id = 1")
            row = cur.fetchone()
            brain_lvl = row["brain_level"] if row else 1
            brain_xp = row["experience_points"] if row else 0
            trades_analyzed = row["total_trades_analyzed"] if row else 0

        return {
            "db_name": "apex_brain.db",
            "db_path": self.db_path,
            "file_size_kb": file_size_kb,
            "brain_level": brain_lvl,
            "experience_points": brain_xp,
            "trades_analyzed": trades_analyzed,
            "evolved_strategies_count": strat_count,
            "learning_journal_entries": journal_count,
            "learned_market_patterns": pattern_count,
            "evolution_checkpoints": checkpoint_count,
            "storage_type": "SQLite 3 Relational Database"
        }

# Global database instance singleton
brain_db = BrainDatabase()
