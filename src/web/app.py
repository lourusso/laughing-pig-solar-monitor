from __future__ import annotations
from pathlib import Path
from typing import Optional, Any, Dict, List
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

    # Memory cache for web pages:
    # We read the HTML page templates once into memory when starting up.
    # Think of this like memorizing a bedtime story so you don't have to walk over
    # to the bookshelf and open the book every single time someone asks to hear it!
    index_html_cache: str = ""
    index_file = templates_dir / "index.html"
    if index_file.exists():
        index_html_cache = index_file.read_text(encoding="utf-8")

    device_html_cache: str = ""
    device_file = templates_dir / "device.html"
    if device_file.exists():
        device_html_cache = device_file.read_text(encoding="utf-8")

    @app.middleware("http")
    async def manage_cache_headers(request, call_next):
        response = await call_next(request)
        # If someone is asking for live solar telemetry numbers under "/api/...",
        # we tell their browser: "Always grab fresh numbers! Don't keep old expired numbers."
        # But for pictures, CSS styles, and scripts, we let the browser cache them so it loads super fast!
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        if index_html_cache:
            return HTMLResponse(content=index_html_cache)
        return HTMLResponse("<h1>Laughing Pig Solar Monitor</h1>")

    @app.get("/device/{device_id}", response_class=HTMLResponse)
    def device_detail(device_id: str):
        if device_html_cache:
            return HTMLResponse(content=device_html_cache)
        return HTMLResponse("<h1>Device Page Not Found</h1>", status_code=404)

    @app.get("/api/live")
    def get_live():
        # First, check our fast computer memory in the service.
        # This gives us an instant answer in less than a millisecond without bothering the hard drive!
        if service and hasattr(service, "get_live_snapshot"):
            return service.get_live_snapshot()
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
