from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
from app.services.mqtt_service import publish_iot_command

router = APIRouter()

class InfraReport(BaseModel):
    description: str
    lat: float
    lon: float
    type: str # 'PUMP', 'DRAIN', 'ROAD'

@router.post("/report")
async def report_issue(report: InfraReport):
    """Receives citizen report and triggers IoT action via MQTT."""
    print(f"📥 Received Report: {report.description}")
    
    # Map Type to Hardware Command
    if report.type == "PUMP":
        command = {"action": "lock_valve", "target": "servo_1", "state": "closed"}
    elif report.type == "DRAIN":
        command = {"action": "insert_block", "target": "servo_2", "state": "blocked"}
    elif report.type == "ROAD":
        command = {"action": "alert_light", "target": "led_red", "state": "on"}
    else:
        raise HTTPException(status_code=400, detail="Unknown Infra Type")
        
    await publish_iot_command(command)
    return {"status": "accepted", "ticket_id": "INF-999", "iot_trigger": True}
