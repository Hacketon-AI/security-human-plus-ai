from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
import time

app = FastAPI()

class CompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]

@app.post("/v1/chat/completions")
async def completions(req: CompletionRequest):
    return {
        "id": "mock-local-amd-response",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "{\"finding_complexity\":\"medium\",\"suggested_route\":\"local_amd_model\",\"summary\":\"Mock AMD local model classified sanitized finding safely.\",\"confidence\":0.82}"
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 40,
            "total_tokens": 90
        }
    }

@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "local-amd-model-mock"
    }
