from fastapi import APIRouter
from app.services.ai_agent import analyze_eligibility

router = APIRouter()

class UserApplication(BaseModel):
    name: str
    age: int
    income: float
    scheme_id: str

@router.get("/list")
def list_schemes():
    return [
        {"id": "MGNREGA", "name": "Rural Employment Guarantee"},
        {"id": "OLD_AGE_PENSION", "name": "Senior Citizen Pension"},
        {"id": "VIDHWA_PENSION", "name": "Widow Support Scheme"}
    ]

@router.post("/apply")
async def apply_scheme(app_data: UserApplication):
    """Uses AI Agent to check eligibility dynamically."""
    result = analyze_eligibility(app_data.dict())
    return result
