from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn
import json
from jsonschema import validate, ValidationError
from pathlib import Path
import datetime

app = FastAPI(title="V1 Strict Schema Tool Server")

schema = json.loads((Path(__file__).parent / "schema.json").read_text())

TOOLS_METADATA = {
    "tools": [
        {
            "id": "normalize_value_case_intake",
            "name": "Normalize Value Case Intake",
            "description": "Validates tool args strictly against JSON Schema (V1 validation).",
            "input_schema": schema
        }
    ]
}

@app.get("/.well-known/mcp")
async def well_known():
    return JSONResponse(TOOLS_METADATA)

@app.post("/run/normalize_value_case_intake")
async def run_tool(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    try:
        validate(instance=payload, schema=schema)
    except ValidationError as e:
        return JSONResponse(
            status_code=400,
            content={
                "qa_status": "FAIL",
                "error": "schema_validation_error",
                "message": str(e),
                "path": list(e.relative_path),
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "qa_status": "PASS",
            "normalized": payload,
            "server_time": datetime.datetime.utcnow().isoformat() + "Z",
        },
    )

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port)