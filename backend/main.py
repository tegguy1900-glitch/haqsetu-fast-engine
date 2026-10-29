from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.routers import infra, schemes

app = FastAPI(title="HaqSetu F.A.S.T. Engine v4.0", version="4.0.0")

# Enable CORS for Localhost & Any Origin (Demo Mode)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(infra.router, prefix="/api/infra", tags=["Infrastructure"])
app.include_router(schemes.router, prefix="/api/schemes", tags=["Schemes"])

@app.get("/")
def root():
    return {"status": "HaqSetu Engine Online", "version": "4.0"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
