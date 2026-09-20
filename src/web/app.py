from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from ..storage.database import Database
from ..config import AppConfig

def create_app(db: Database, config: AppConfig, service: Optional[Any] = None) -> FastAPI:
    app = FastAPI(title="Laughing Pig Solar Monitor", version="1.0.0")

    base_dir = Path(__file__).parent
    static_dir = base_dir / "static"
    templates_dir = base_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_file = templates_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Laughing Pig Solar Monitor</h1>")

    @app.get("/device/{device_id}", response_class=HTMLResponse)
    def device_detail(device_id: str):
        device_file = templates_dir / "device.html"
        if device_file.exists():
            return HTMLResponse(content=device_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Device Page Not Found</h1>", status_code=404)

    @app.get("/api/live")
    def get_live():
        latest = db.get_latest_snapshot()
        return latest or {}

    @app.get("/api/device/{device_id}")
    def get_device(device_id: str):
        if service and hasattr(service, "get_device_telemetry"):
            return service.get_device_telemetry(device_id)
        return {"error": "Device telemetry service unavailable"}

    @app.get("/api/history")
    def get_history(hours: int = 24):
        return db.get_history(hours=hours)

    @app.get("/api/export")
    def export_csv(days: int = 7):
        csv_data = db.export_csv(days=days)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=solar_telemetry_{days}d.csv"}
        )

    return app
