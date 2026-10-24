import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.api.routes import router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="SkyReady - AI/ML Predictive Maintenance & Google OR-Tools CP-SAT Fleet Availability Optimizer for Ministry of Defence / DSSC."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes under /api
app.include_router(router, prefix="/api")

# Serve Web Dashboard
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
frontend_dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=FileResponse)
def root_dashboard():
    # If React frontend/dist exists and has index.html, prioritize built SPA
    if os.path.exists(frontend_dist_dir):
        spa_index = os.path.join(frontend_dist_dir, "index.html")
        if os.path.exists(spa_index):
            return FileResponse(spa_index)
            
    # Default to high-fidelity Tactical C2 dashboard
    static_index = os.path.join(static_dir, "index.html")
    if os.path.exists(static_index):
        return FileResponse(static_index)
        
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/dashboard", response_class=FileResponse)
def get_dashboard():
    static_index = os.path.join(static_dir, "index.html")
    return FileResponse(static_index)

@app.get("/health")
def health_check():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "problem_statement_id": settings.PROBLEM_STATEMENT_ID,
        "team": settings.TEAM_NAME,
        "status": "OPERATIONAL",
        "endpoints": {
            "dashboard": "/dashboard",
            "fleet": "/api/fleet",
            "schedule": "/api/optimizer/schedule",
            "simulator": "/api/simulator/what-if",
            "spares": "/api/spares",
            "audit": "/api/audit/logs",
            "docs": "/docs"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
