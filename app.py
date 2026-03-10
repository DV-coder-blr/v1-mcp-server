import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount

from jsonschema import Draft202012Validator

from mcp.server.fastmcp import FastMCP


# -----------------------------
# Your existing tool schema
# -----------------------------
INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["client", "use_case", "currency", "assumptions"],
    "properties": {
        "client": {"type": "string", "minLength": 1},
        "use_case": {"type": "string", "minLength": 1},
        "currency": {"type": "string", "enum": ["USD", "EUR", "GBP", "INR"]},
        "assumptions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["assumption_id", "name", "value", "units", "scenario", "source"],
                "properties": {
                    "assumption_id": {"type": "string", "pattern": r"^A[0-9]{3}$"},
                    "name": {"type": "string", "minLength": 1},
                    "value": {"type": "number"},
                    "units": {"type": "string", "minLength": 1},
                    "scenario": {"type": "string", "enum": ["Base", "Conservative", "Aggressive"]},
                    "source": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "reference"],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["internal", "public_report", "benchmark", "expert_judgment"],
                            },
                            "reference": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        },
    },
}

_validator = Draft202012Validator(INPUT_SCHEMA)


# -----------------------------
# MCP server (real MCP protocol)
# -----------------------------
# json_response=True makes MCP responses JSON (good for web clients)
mcp = FastMCP("ValueCase V1", json_response=True)

@mcp.tool(name="normalize_value_case_intake")
def normalize_value_case_intake(payload: dict) -> dict:
    """
    Validates tool args strictly against JSON Schema (V1 validation).
    Returns qa_status PASS/FAIL plus either normalized payload or error detail.
    """
    errors = sorted(_validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        # deterministic FAIL structure for V1
        return {
            "qa_status": "FAIL",
            "error": "schema_validation_error",
            "message": errors[0].message,
            "path": list(errors[0].path),
        }

    # In V1 we simply echo back as "normalized"
    return {"qa_status": "PASS", "normalized": payload}


# -----------------------------
# Mount MCP at /mcp (Streamable HTTP)
# -----------------------------
# from starlette.middleware.trustedhost import TrustedHostMiddleware

# # Create the MCP streamable HTTP ASGI app
# inner_app = mcp.streamable_http_app()

# # Apply TrustedHostMiddleware to the INNER app (most important)
# inner_app.add_middleware(
#     TrustedHostMiddleware,
#     allowed_hosts=["*"],  # V1: allow all hosts to avoid Render host/header issues
# )

# @contextlib.asynccontextmanager
# async def lifespan(app: Starlette):
#     async with mcp.session_manager.run():
#         yield

# # Wrap with Starlette only to manage lifespan/session
# app = Starlette(
#     routes=[Mount("/", app=inner_app)],
#     lifespan=lifespan,
# )

# # Also apply to OUTER app (belt-and-suspenders)
# app.add_middleware(
#     TrustedHostMiddleware,
#     allowed_hosts=["*"],
# )

import contextlib
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route, Mount
from starlette.middleware.trustedhost import TrustedHostMiddleware

# keep your existing: mcp = FastMCP(...), tool definition, lifespan manager, etc.

def ping(request):
    return PlainTextResponse("pong-v1-mcp-server")

inner_app = mcp.streamable_http_app()

@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield

app = Starlette(
    routes=[
        Route("/ping", ping),
        Mount("/mcp", app=inner_app),
    ],
    lifespan=lifespan,
    redirect_slashes=True,
)

# Make host checks fully permissive for V1
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])