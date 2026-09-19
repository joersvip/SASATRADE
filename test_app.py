import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

print("1. Testing Static Assets:")
for path in ["/", "/css/style.css", "/js/chart.js", "/js/app.js", "/js/sounds.js"]:
    r = client.get(path)
    print(f"   {path} -> Status {r.status_code}, Length: {len(r.content)} bytes")

print("\n2. Testing State & Markets:")
r = client.get("/api/state")
state = r.json()
print(f"   Markets count: {len(state['markets'])}")
print(f"   Sample symbols: {[m['symbol'] for m in state['markets'][:6]]}")
print(f"   Active Account: {state['active_account']['name']} (${state['active_account']['balance']:,.2f})")
print(f"   Open Positions: {len(state['open_positions'])}")
print(f"   History Trades: {len(state['history'])}")

print("\n3. Testing Account Creation & Switch:")
r = client.post("/api/accounts/create", json={"name": "Demo AI Test $25k", "type": "demo", "initial_balance": 25000, "leverage": 200})
new_acc = r.json()["account"]
print(f"   Created Account: {new_acc['id']} - {new_acc['name']}")

r = client.post("/api/accounts/switch", json={"account_id": new_acc["id"]})
print(f"   Switched Active Account -> {r.json()['active_account']['name']}")

print("\n4. Testing Multi-Market Order Execution:")
for sym, cat in [("XAUUSD", "Forex/Emas"), ("BTCUSDT", "Crypto"), ("NVDA", "Saham")]:
    r = client.post("/api/order/open", json={"symbol": sym, "direction": "BUY", "lot": 0.2, "strategy": f"AI Test {cat}"})
    pos = r.json()["position"]
    print(f"   Opened BUY {sym} ({cat}) -> ID: {pos['id']}, Entry: {pos['entry_price']}, SL: {pos['sl']}, TP: {pos['tp']}")

print("\n5. Testing AI Force Scan:")
r = client.post("/api/ai/scan-now")
print(f"   AI Scan triggered -> Recent signals: {len(r.json()['recent_signals'])}")

print("\n6. Testing Account Reset:")
r = client.post("/api/accounts/reset", json={"account_id": new_acc["id"], "new_balance": 25000})
print(f"   Reset Account Balance -> ${r.json()['account']['balance']:,.2f}")

print("\n8. Testing AI Backtest Laboratorium:")
for test_sym, test_strat in [("BTCUSDT", "scalping"), ("EURUSD", "reversal")]:
    bt_res = client.post("/api/ai/backtest", json={
        "symbol": test_sym,
        "strategy_id": test_strat,
        "initial_balance": 10000,
        "risk_pct": 1.0,
        "confidence_threshold": 60
    })
    assert bt_res.status_code == 200, f"Backtest failed: {bt_res.text}"
    bt_data = bt_res.json()
    assert bt_data["success"] is True
    m = bt_data["metrics"]
    print(f"   Backtest {test_sym} ({test_strat}): Analyzed {bt_data['candles_analyzed']} bars, Trades: {m['total_trades']}, WinRate: {m['win_rate_pct']}%, Net Profit: ${m['net_profit']:.2f} ({m['net_profit_pct']}%), PF: {m['profit_factor']}, MaxDD: {m['max_drawdown_pct']}%")

print("\n9. Testing Circuit Breaker & Emergency Kill-Switch:")
cb_status = client.get("/api/risk/circuit-breaker").json()
print(f"   Circuit Breaker Initial: Tripped={cb_status['circuit_breaker']['tripped']}, Daily Loss={cb_status['circuit_breaker']['daily_loss_pct']:.2f}%")

# Open a test trade on active demo account to verify kill switch closes it
open_r = client.post("/api/order/open", json={"symbol": "EURUSD", "direction": "BUY", "lot": 0.1, "strategy": "KillSwitch Test"})
assert open_r.status_code == 200, f"Order open failed: {open_r.text}"

# Trigger Kill Switch
ks_res = client.post("/api/risk/kill-switch")
assert ks_res.status_code == 200, f"Kill switch failed: {ks_res.text}"
ks_data = ks_res.json()
print(f"   Triggered Kill-Switch: {ks_data['message']}")
assert ks_data["status"]["circuit_breaker"]["tripped"] is True
assert len(ks_data["status"]["open_positions"]) == 0
assert ks_data["status"]["ai_mode"] == "paused"

# Reset Circuit Breaker
cb_reset = client.post("/api/risk/circuit-breaker/reset")
assert cb_reset.status_code == 200
reset_data = cb_reset.json()
print(f"   Reset Circuit Breaker: Tripped={reset_data['circuit_breaker']['tripped']}")
assert reset_data["circuit_breaker"]["tripped"] is False

print("\n10. Testing Self-Learning AI Brain & Memory:")
lrn_res = client.get("/api/ai/learning-stats")
assert lrn_res.status_code == 200
lrn_data = lrn_res.json()["learning"]
print(f"   Initial Brain State: Level {lrn_data['brain_level']}, XP: {lrn_data['experience_points']}/{lrn_data['next_level_xp']}, Trades Analyzed: {lrn_data['total_trades_analyzed']}")
init_xp = lrn_data['experience_points']

# Open and close a trade to trigger learning feedback loop
open_trade = client.post("/api/order/open", json={"symbol": "GBPUSD", "direction": "BUY", "lot": 0.1, "strategy": "Neural Momentum Trend"}).json()["position"]
close_res = client.post(f"/api/order/close/{open_trade['id']}").json()
assert close_res["success"] is True

# Verify learning stats updated
lrn_updated = client.get("/api/ai/learning-stats").json()["learning"]
print(f"   Post-Trade Brain State: Level {lrn_updated['brain_level']}, XP: {lrn_updated['experience_points']}, Analyzed: {lrn_updated['total_trades_analyzed']}")
assert lrn_updated["experience_points"] > init_xp
assert len(lrn_updated["recent_insights"]) > 0
print(f"   Latest AI Insight: {lrn_updated['recent_insights'][0]['message'].encode('ascii', 'replace').decode('ascii')}")

print("\n11. Testing Internet Market Intelligence & High-Impact News Shield:")
intel_r = client.get("/api/ai/market-intel")
assert intel_r.status_code == 200, f"Market intel failed: {intel_r.text}"
intel_data = intel_r.json()
print(f"   Events Loaded: {len(intel_data.get('events', []))}, News Loaded: {len(intel_data.get('news', []))}")
print(f"   Macro Sentiment: {intel_data.get('sentiment')} ({intel_data.get('sentiment_score', 0):+.1f}%)")
print(f"   News Shield Active: {intel_data.get('news_shield', {}).get('shield_active', False)}")

print("\n12. Testing Autonomous AI Strategy Lab:")
strat_r = client.get("/api/ai/strategies")
assert strat_r.status_code == 200, f"Strategies endpoint failed: {strat_r.text}"
strat_data = strat_r.json()
print(f"   Total Catalog Strategies: {len(strat_data.get('strategies', {}))}, Custom: {strat_data.get('custom_count', 0)}")
print(f"   Experience Weakness Analysis: {strat_data.get('experience_analysis', {}).get('weakness')}")

# Test Generating a new strategy
gen_r = client.post("/api/ai/generate-strategy", json={"symbol": "BTCUSDT"})
assert gen_r.status_code == 200, f"Strategy generation failed: {gen_r.text}"
gen_data = gen_r.json()
assert gen_data.get("success") is True, f"Generation not successful: {gen_data}"
new_strat = gen_data["strategy"]
metrics = gen_data.get("metrics") or new_strat.get("backtest_results", {})
wr = metrics.get("win_rate", 0)
pf = metrics.get("profit_factor", 0)
print(f"   Synthesized Strategy: '{new_strat['name']}' (Win-Rate: {wr}%, PF: {pf})")

# Clean up the generated strategy
clean_r = client.delete(f"/api/ai/strategies/{new_strat['id']}")
assert clean_r.status_code == 200, f"Clean strategy failed: {clean_r.text}"
print(f"   Cleaned up test strategy: {new_strat['id']}")

print("\n13. Testing SQLite AI Brain Database (apex_brain.db):")
db_r = client.get("/api/ai/brain-db/stats")
assert db_r.status_code == 200, f"Brain DB stats failed: {db_r.text}"
db_data = db_r.json()
assert db_data.get("success") is True
print(f"   Database Name: {db_data.get('db_name')}")
print(f"   Database Size: {db_data.get('file_size_kb')} KB")
print(f"   Evolved Strategies in DB: {db_data.get('evolved_strategies_count')}")
print(f"   Learning Journal Entries: {db_data.get('learning_journal_entries')}")
print(f"   Learned Patterns in DB: {db_data.get('learned_market_patterns')}")
print(f"   Storage Architecture: {db_data.get('storage_type')}")

print("\n14. Testing Account Deletion & Cleanup:")
del_r = client.delete(f"/api/accounts/{new_acc['id']}")
assert del_r.status_code == 200, f"Delete failed: {del_r.text}"
del_data = del_r.json()
print(f"   Deleted Account: {new_acc['id']} -> Success: {del_data.get('success')}")
print(f"   Remaining Accounts Count: {len(del_data.get('accounts', []))}")
print(f"   New Active Account: {del_data.get('active_account', {}).get('name')}")

print("\nAll Tests Completed Successfully!")
