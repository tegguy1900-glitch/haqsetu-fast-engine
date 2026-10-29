"""
The Central Mesh Server
Aggregates telemetry and serves the Heatwave UI.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import os

# Import the beacon
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mesh.telemetry_beacon import generate_telemetry

app = FastAPI()

# Allow the web UI to fetch data
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/telemetry")
def get_mesh_data():
    """The endpoint the Heatwave Map polls every 2 seconds."""
    return generate_telemetry()

@app.get("/")
def serve_map():
    """Serves the HTML dashboard."""
    return FileResponse("web/heatwave_map.html")

if __name__ == "__main__":
    print("🌐 Starting National Heatwave Mesh on port 8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001)