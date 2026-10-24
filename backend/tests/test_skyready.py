import sys
import os
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app
from app.data.fleet_generator import get_fleet_state, SPARE_CATALOG, HANGAR_BAYS, TECHNICIANS
from app.ml.anomaly_detector import anomaly_detector
from app.ml.rul_predictor import rul_predictor
from app.ml.explainer import explainer_service
from app.optimizer.fleet_optimizer import fleet_optimizer
from app.simulator.what_if_engine import what_if_engine
from app.services.audit_service import audit_service

client = TestClient(app)

def test_fleet_generation():
    state = get_fleet_state()
    fleet = state["fleet"]
    assert len(fleet) == 24, "Fleet must contain exactly 24 aircraft"
    assert len(state["bays"]) == 3, "Must have 3 hangar bays"
    assert len(state["technicians"]) == 12, "Must have 12 technicians"

    for ac in fleet:
        assert "tail_number" in ac
        assert "status" in ac
        assert "health_score" in ac
        assert "rul" in ac
        assert "maintenance_spec" in ac
        assert len(ac["recent_telemetry"]) > 0

def test_anomaly_detection_healthy_vs_degraded():
    # Healthy nominal point
    healthy_point = {
        "T50_EGT": 1402.0,
        "T30_HPC": 1586.0,
        "P30_Press": 553.2,
        "Nc_Core": 9052.0,
        "vibration": 0.125,
        "BPR": 8.43,
        "fuel_flow_phi": 521.6
    }
    healthy_res = anomaly_detector.score_telemetry(healthy_point)
    assert healthy_res["anomaly_score"] < 60.0, "Healthy telemetry should have low anomaly score"
    assert healthy_res["severity"] == "NOMINAL"

    # Acute degraded point (EGT high, vibration high)
    degraded_point = {
        "T50_EGT": 1495.0,
        "T30_HPC": 1620.0,
        "P30_Press": 535.0,
        "Nc_Core": 9180.0,
        "vibration": 0.45,
        "BPR": 8.20,
        "fuel_flow_phi": 538.0
    }
    degraded_res = anomaly_detector.score_telemetry(degraded_point)
    assert degraded_res["anomaly_score"] >= 65.0, "Degraded telemetry must trigger elevated anomaly score"
    assert len(degraded_res["flagged_symptoms"]) > 0

def test_rul_quantile_estimator():
    telemetry = {
        "T50_EGT": 1480.0,
        "T30_HPC": 1610.0,
        "P30_Press": 540.0,
        "Nc_Core": 9150.0,
        "vibration": 0.38,
        "BPR": 8.25,
        "fuel_flow_phi": 535.0
    }
    rul = rul_predictor.predict_rul(telemetry)
    assert rul["p10_pessimistic"] <= rul["p50_median"] <= rul["p90_optimistic"], "Quantiles must follow P10 <= P50 <= P90"
    assert rul["safe_days_remaining"] >= 1, "Safe days must be positive integer"

def test_shap_explainability_and_narrative():
    state = get_fleet_state()
    ac = state["fleet"][2] # IAF-SK-103
    explanation = explainer_service.explain_aircraft(ac)

    assert "top_drivers" in explanation
    assert len(explanation["top_drivers"]) > 0
    assert "narrative" in explanation
    assert len(explanation["narrative"]) > 20, "Must synthesize narrative for flight-line crew"
    assert "recommendation" in explanation

    # SHAP driver percentage check
    total_pct = sum(d["contribution_pct"] for d in explanation["all_drivers"])
    assert 95.0 <= total_pct <= 105.0, "SHAP contributions must sum to approximately 100%"

def test_cpsat_fleet_optimizer_execution():
    plan = fleet_optimizer.optimize_schedule()
    assert plan["solver_status"] in ["OPTIMAL", "FEASIBLE"]
    assert plan["solve_time_ms"] < 2000.0, "Optimization must solve in <2 seconds"
    assert plan["fleet_availability_rate_pct"] >= 80.0, "Target fleet availability must meet or exceed 80%"
    assert plan["availability_gain_pts"] >= 5.0, "Gain must exceed +5.0 points vs reactive benchmark"
    assert len(plan["scheduled_interventions"]) > 0

    # Verify no hangar bay overlaps
    bay_intervals = {}
    for task in plan["scheduled_interventions"]:
        bay = task["bay_id"]
        start = task["start_day"]
        end = task["end_day"]
        if bay not in bay_intervals:
            bay_intervals[bay] = []
        for s, e in bay_intervals[bay]:
            assert end <= s or start >= e, f"Hangar overlap detected in {bay}: ({start}, {end}) vs ({s}, {e})"
        bay_intervals[bay].append((start, end))

def test_what_if_stress_simulation():
    sim = what_if_engine.run_simulation(
        spares_delay_days=3,
        demand_surge_multiplier=1.2,
        closed_bay_id="Bay-1",
        technician_shortage_pct=20
    )
    assert "baseline" in sim
    assert "scenario" in sim
    assert "impact" in sim
    assert "contingency_mitigations" in sim
    assert len(sim["contingency_mitigations"]) > 0
    assert len(sim["comparative_timeline"]) == 30
    assert sim["impact"]["delta_availability_pct"] <= 0.0, "Adverse conditions should degrade or maintain availability"

def test_sha256_cryptographic_audit_ledger():
    # Verify initial ledger integrity
    verify_res = audit_service.verify_integrity()
    assert verify_res["is_valid"] is True
    assert verify_res["status"] in ["ALL_SIGNATURES_VERIFIED", "CRYPTOGRAPHIC_INTEGRITY_VERIFIED"]

    # Add new entry
    new_entry = audit_service.record_entry(
        operator_id="SqnLdr Test",
        operator_rank="Officer",
        action="TEST_RELEASE",
        details="Unit test entry",
        justification="Automated verification test"
    )
    assert new_entry["index"] > 1
    assert len(new_entry["current_hash"]) == 64

    # Verify chain integrity after addition
    verify_after = audit_service.verify_integrity()
    assert verify_after["is_valid"] is True
    assert verify_after["latest_hash"] == new_entry["current_hash"]

def test_api_rest_endpoints():
    # Dashboard HTML endpoint
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "text/html" in r_dash.headers["content-type"]

    # Health JSON endpoint
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "OPERATIONAL"

    # Fleet Overview
    r_fleet = client.get("/api/fleet")
    assert r_fleet.status_code == 200
    assert r_fleet.json()["kpis"]["total_aircraft"] == 24

    # Aircraft Detail
    r_ac = client.get("/api/fleet/IAF-SK-103")
    assert r_ac.status_code == 200
    assert r_ac.json()["aircraft"]["tail_number"] == "IAF-SK-103"

    # CP-SAT Schedule
    r_sched = client.get("/api/optimizer/schedule")
    assert r_sched.status_code == 200
    assert r_sched.json()["solver_status"] in ["OPTIMAL", "FEASIBLE"]

    # What-If Simulator POST
    r_sim = client.post("/api/simulator/what-if", json={
        "spares_delay_days": 2,
        "demand_surge_multiplier": 1.1,
        "closed_bay_id": "None",
        "technician_shortage_pct": 0
    })
    assert r_sim.status_code == 200
    assert "scenario" in r_sim.json()

    # Spares Inventory
    r_spares = client.get("/api/spares")
    assert r_spares.status_code == 200
    assert len(r_spares.json()["spares"]) > 0

    # Audit Logs & Verify
    r_logs = client.get("/api/audit/logs")
    assert r_logs.status_code == 200
    r_v = client.get("/api/audit/verify")
    assert r_v.status_code == 200
    assert r_v.json()["is_valid"] is True

if __name__ == "__main__":
    pytest.main(["-v", __file__])
