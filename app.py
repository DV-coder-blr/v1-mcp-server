import contextlib

from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP

from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route


# -----------------------------
# V1: Strict input schema
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
                "required": [
                    "assumption_id",
                    "name",
                    "value",
                    "units",
                    "scenario",
                    "source",
                ],
                "properties": {
                    "assumption_id": {"type": "string", "pattern": r"^A[0-9]{3}$"},
                    "name": {"type": "string", "minLength": 1},
                    "value": {"type": "number"},
                    "units": {"type": "string", "minLength": 1},
                    "scenario": {
                        "type": "string",
                        "enum": ["Base", "Conservative", "Aggressive"],
                    },
                    "source": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "reference"],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "internal",
                                    "public_report",
                                    "benchmark",
                                    "expert_judgment",
                                ],
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
# MCP Server (Streamable HTTP)
# -----------------------------
# IMPORTANT:
# - streamable_http_path="/" makes MCP endpoints live at the ROOT of the mount.
#   So mounting at /mcp means the MCP endpoint is /mcp (not /mcp/mcp).
mcp = FastMCP(
    "ValueCase V1",
    json_response=True,
    stateless_http=True,
    streamable_http_path="/",
)


@mcp.tool(name="normalize_value_case_intake")
def normalize_value_case_intake(payload: dict) -> dict:
    """
    V1 validation tool: strictly validates payload against JSON Schema.
    """
    errors = sorted(_validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        e0 = errors[0]
        return {
            "qa_status": "FAIL",
            "error": "schema_validation_error",
            "message": e0.message,
            "path": list(e0.path),
        }

    return {"qa_status": "PASS", "normalized": payload}


# -----------------------------
# App wiring (Render-friendly)
# -----------------------------
def ping(request):
    return PlainTextResponse("pong-v1-mcp-server")


# Create the MCP ASGI app, then wrap it with TrustedHostMiddleware (ASGI-safe)
inner_app = mcp.streamable_http_app()
inner_app = TrustedHostMiddleware(inner_app, allowed_hosts=["*"])


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    # Ensures MCP session manager is active
    async with mcp.session_manager.run():
        yield


# Mount MCP under /mcp AND /mcp/ to avoid trailing-slash issues
app = Starlette(
    routes=[
        Route("/ping", ping),
        Mount("/mcp", app=inner_app),
        Mount("/mcp/", app=inner_app),
    ],
    lifespan=lifespan,
)

# Also allow all hosts at the outer layer (belt-and-suspenders)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])