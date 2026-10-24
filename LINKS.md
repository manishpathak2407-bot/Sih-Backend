# SkyReady (SIH26249) — Master Links & Operational Directory

> **Repository:** [manishpathak2407-bot/SkyReady](https://github.com/manishpathak2407-bot/SkyReady)  
> **Backup Branch:** [manishpathak2407-bot/Sih-Backend (branch: `skyready`)](https://github.com/manishpathak2407-bot/Sih-Backend/tree/skyready)  
> **Problem Statement ID:** 26249 | **Ministry of Defence (MoD) / Defence Services Staff College (DSSC)**  
> **System:** Predictive Maintenance & Google OR-Tools CP-SAT Fleet Availability Optimizer  
> **Operational Target:** No. 45 Flying Daggers Squadron (24 Multirole Twin-Engine Fighters, AFS Sulur)  
> **Team:** ZEN / KILLSWITCHX  

---

## 1. Primary Tactical Web Dashboard Links

| Target | Description | URL Link |
| :--- | :--- | :--- |
| **Tactical C2 Web Dashboard (Primary)** | Main interactive defense platform (Fleet Command, Digital Twin, SHAP Explain, CP-SAT Plan, What-If Simulator, Audit Ledger) | **[http://localhost:8000/](http://localhost:8000/)** |
| **Alternative Loopback Address** | Fallback loopback address for the web dashboard | **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** |
| **Dashboard Explicit Route** | Direct route alias to the Tactical C2 Single-Page Application | **[http://localhost:8000/dashboard](http://localhost:8000/dashboard)** |
| **Local Network / Mobile Stream** | Access from mobile device or evaluator laptop on same Wi-Fi (replace `<HOST_IP>` via `ipconfig`) | `http://<HOST_IP>:8000/` |

---

## 2. Interactive API Documentation & Service Health

| Target | Description | URL Link |
| :--- | :--- | :--- |
| **Swagger Interactive OpenAPI Docs** | Live interactive Swagger UI to test endpoints, trigger CP-SAT solver, run what-if simulations, and inspect JSON responses | **[http://localhost:8000/docs](http://localhost:8000/docs)** |
| **ReDoc API Reference** | Clean, structured OpenAPI specifications and model schemas | **[http://localhost:8000/redoc](http://localhost:8000/redoc)** |
| **Raw OpenAPI Schema** | Machine-readable OpenAPI 3.1 JSON definition | **[http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)** |
| **Service Discovery & Health Check** | Operational status, version tag, and endpoint registry | **[http://localhost:8000/health](http://localhost:8000/health)** |

---

## 3. Core Analytical & Operational REST API Endpoints

| Endpoint | Method | Operational Function | Example URL |
| :--- | :---: | :--- | :--- |
| **Squadron Readiness Matrix** | `GET` | 24-aircraft fleet status, anomaly scores, RUL quantiles ($P_{10}, P_{50}, P_{90}$), and availability rate | **[http://localhost:8000/api/fleet](http://localhost:8000/api/fleet)** |
| **Fighter Digital Twin & SHAP** | `GET` | C-MAPSS telemetry curves (EGT, vibration, core RPM, HPC pressure) + SHAP root-cause breakdown | **[http://localhost:8000/api/fleet/IAF-SK-101](http://localhost:8000/api/fleet/IAF-SK-101)** |
| **CP-SAT Master Schedule** | `GET` | Google OR-Tools 30-day master maintenance schedule, hangar allocations, technician shifts & daily readiness | **[http://localhost:8000/api/optimizer/schedule](http://localhost:8000/api/optimizer/schedule)** |
| **Dynamic Re-Solve Schedule** | `POST` | Re-runs Google OR-Tools CP-SAT with custom parameters (returns optimal solution in ~27 ms) | `http://localhost:8000/api/optimizer/run` |
| **What-If Stress Simulator** | `POST` | Real-time stress simulation across supply delays, sortie surges, bay closures & technician deficits | `http://localhost:8000/api/simulator/what-if` |
| **Depot Spares & Resources** | `GET` | Critical spares catalog, stock levels, procurement lead times, hangar bays & specialist rosters | **[http://localhost:8000/api/spares](http://localhost:8000/api/spares)** |
| **SHA-256 Audit Trail** | `GET` | Cryptographically chained immutable audit records for MoD compliance | **[http://localhost:8000/api/audit/logs](http://localhost:8000/api/audit/logs)** |
| **Officer Action Signing** | `POST` | Records human-in-the-loop release-to-service sign-offs and emergency overrides | `http://localhost:8000/api/audit/action` |
| **Blockchain Chain Verification** | `GET` | Validates entire SHA-256 cryptographic hash pointer sequence to prove zero tampering | **[http://localhost:8000/api/audit/verify](http://localhost:8000/api/audit/verify)** |

---

## 4. Technical Architecture, Presentation & PDF Specifications

| Document | Format | Description | File Path |
| :--- | :---: | :--- | :--- |
| **Official Architecture Specification** | `.pdf` | Complete 6-page comprehensive engineering whitepaper & system specification | **[SkyReady_Architecture.pdf](SkyReady_Architecture.pdf)** |
| **High-Fidelity Architecture Report** | `.html` | Printable A4 technical architecture with styling and charts | **[generate_architecture_pdf.html](generate_architecture_pdf.html)** |
| **Official Hackathon Presentation** | `.pptx` | 16:9 defense evaluation presentation deck | **[SKY ROCKET.pptx](SKY%20ROCKET.pptx)** |
| **Engineering Readme & Guide** | `.md` | Architectural breakdown, benchmarks, and mathematical models | **[README.md](README.md)** |

---

## 5. GitHub Repository & Codebase Links

| Destination | Purpose | URL Link |
| :--- | :--- | :--- |
| **GitHub Primary Repository** | Standalone repository for SkyReady | **[https://github.com/manishpathak2407-bot/SkyReady](https://github.com/manishpathak2407-bot/SkyReady)** |
| **Synchronized Branch** | Active synchronized branch on Sih-Backend | **[https://github.com/manishpathak2407-bot/Sih-Backend/tree/skyready](https://github.com/manishpathak2407-bot/Sih-Backend/tree/skyready)** |
| **Issue Tracker** | Issue submission and feature requests | **[https://github.com/manishpathak2407-bot/SkyReady/issues](https://github.com/manishpathak2407-bot/SkyReady/issues)** |

---

## 6. Local Startup Instructions

### Quick Launch via PowerShell:
```powershell
cd C:\Users\manis\SkyReady
.\start.ps1
```

### Quick Launch via Batch File:
Double-click `start.bat` or run:
```cmd
cd C:\Users\manis\SkyReady
start.bat
```

The system will start and be immediately available at **[http://localhost:8000/](http://localhost:8000/)**.
