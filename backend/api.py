from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import asyncio
from backend.main import process_query

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_query: str
    previous_system_response: Optional[str] = ""
    full_history: Optional[str] = ""
    user_id: Optional[str] = "anonymous"
    state: Optional[Dict[str, Any]] = None

@app.post("/api/chat/process")
async def process_chat(request: ChatRequest):
    try:
        # Process the query using the existing function
        response = await process_query(
            user_query=request.user_query,
            previous_system_response=request.previous_system_response,
            full_history=request.full_history,
            state=request.state
        )
        
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
