# Suppress warnings before any imports
import os
import sys
import warnings
import logging
from pathlib import Path

# Limit BLAS/OpenMP threads before numpy/scipy/torch are imported downstream
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded from .env file")
except ImportError:
    print("⚠️ python-dotenv not installed, environment variables may not be loaded")
except Exception as e:
    print(f"⚠️ Error loading .env file: {e}")


# Suppress TensorFlow/MediaPipe warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['ABSL_MIN_LOG_LEVEL'] = '2'
logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('absl').setLevel(logging.ERROR)
warnings.filterwarnings('ignore', message='.*Feedback manager.*')
warnings.filterwarnings('ignore', category=UserWarning, module='langchain')

from fastapi import FastAPI

# Import chatbot router (with error handling for missing dependencies)
try:
    from app.chatbot.api import router as api_router
except Exception as e:
    print(
        f"Warning: Could not load chatbot router ({type(e).__name__}): {e}. "
        "Chat routes will be missing from the app and Swagger."
    )
    import traceback

    traceback.print_exc()
    api_router = None

from app.ai_ingredient_intelligence.api.analyze_inci import router as analyze_inci_router   # ✅ import here

# Import formulation report router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.formulation_report import router as formulation_report_router
except ImportError as e:
    print(f"Warning: Could not import formulation_report router: {e}")
    print("   Formulation Report API will not be available. This is not critical.")
    formulation_report_router = None

from app.ai_ingredient_intelligence.api.cost_calculator import router as cost_calculator_router
from app.ai_ingredient_intelligence.api.ingredient_search import router as ingredient_search_router
from app.ai_ingredient_intelligence.api.market_research import router as market_research_router
from app.ai_ingredient_intelligence.api.distributor_management import router as distributor_management_router
from app.ai_ingredient_intelligence.api.ingredient_costs import router as ingredient_costs_router
from app.ai_ingredient_intelligence.api.ingredient_history import router as ingredient_history_router
from app.ai_ingredient_intelligence.api.product_comparison import router as product_comparison_router
from app.ai_ingredient_intelligence.api.health_checks import router as health_checks_router
from app.hlhp.api.alerts import router as hl_alerts_router
from app.hlhp.api.personalized_alerts import router as hl_personalized_alerts_router
from app.hlhp.api.scan import router as hlhp_scan_router
from app.hlhp.api.composition import router as hlhp_composition_router
from app.hlhp.api.weather import router as hlhp_weather_router
# Import Trend Insights router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.trend_insights import router as trend_insights_router
except ImportError as e:
    print(f"Warning: Could not import trend_insights router: {e}")
    print("   Trend Insights API will not be available. This is not critical.")
    trend_insights_router = None

# Import Formula Generation router (with error handling for missing dependencies)
try:
    from app.ai_ingredient_intelligence.api.formula_generation import router as formula_generation_router
except ImportError as e:
    print(f"Warning: Could not import formula_generation router: {e}")
    print("   Formula Generation API will not be available. This is not critical.")
    formula_generation_router = None

# Import Make a Wish router (consolidated - includes all endpoints)
try:
    from app.ai_ingredient_intelligence.api.make_wish_api_revised import router as make_wish_router
except ImportError as e:
    print(f"Warning: Could not import make_wish router: {e}")
    print("   Make a Wish API will not be available. This is not critical.")
    make_wish_router = None

# Import Notifications router
try:
    from app.ai_ingredient_intelligence.api.notifications import router as notifications_router
except ImportError as e:
    print(f"Warning: Could not import notifications router: {e}")
    print("   Notifications API will not be available. This is not critical.")
    notifications_router = None
# from app.product_listing_image_extraction.route import router as image_extractor_router  # Commented out - module doesn't exist

# Add Face Analysis path to Python path
face_analysis_path = Path(__file__).parent / "faceAnalysis"
sys.path.insert(0, str(face_analysis_path))

# Import Face Analysis router (with error handling for missing module)
try:
    from backend.api.main import router as face_analysis_router  # type: ignore
except ImportError as e:
    print(f"Warning: Could not import face_analysis router: {e}")
    print("   Face Analysis API will not be available. This is not critical.")
    face_analysis_router = None
from fastapi.middleware.cors import CORSMiddleware
from app.ai_ingredient_intelligence.db.collections import distributor_col
from fastapi.openapi.utils import get_openapi
app = FastAPI(
    title="SkinBB API Documentation",
    description="API documentation for SkinBB - An AI assistant for skincare queries with document retrieval and web search fallback",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI - explicitly enabled
    redoc_url="/redoc",  # ReDoc alternative - explicitly enabled
    openapi_url="/openapi.json"  # OpenAPI JSON schema - explicitly enabled
)

# Label Looker (productIngredientScan) — see migration-packet/README-migration.md
try:
    from app.label_looker.bootstrap import install_label_looker

    install_label_looker(app)
except Exception as _ll_exc:
    print(f"Warning: Label Looker not installed ({type(_ll_exc).__name__}): {_ll_exc}")

# Custom OpenAPI schema configuration
def custom_openapi():
    """
    Custom OpenAPI schema with servers, security schemes, and enhanced metadata.
    Similar to swagger-jsdoc configuration but for FastAPI.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    server_url = (os.getenv("SERVER_URL") or "").strip().rstrip("/")
    node_env = os.getenv("NODE_ENV", "development")
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version="3.1.0",
        description=app.description,
        routes=app.routes,
        terms_of_service="https://www.formulynx.in/terms",
        contact={
            "name": "SkinBB API Support",
            "url": "https://www.formulynx.in/contact",
            "email": "support@formulynx.in"
        },
        license_info={
            "name": "Proprietary",
            "url": "https://www.formulynx.in/license"
        },
        tags=[
            {
                "name": "Chatbot",
                "description": "AI-powered skincare chatbot endpoints for querying and document retrieval"
            },
            {
                "name": "INCI Analysis",
                "description": "INCI name analysis and ingredient decoding endpoints"
            },
            {
                "name": "Formulation Reports",
                "description": "Generate comprehensive formulation reports in PDF and PPT formats"
            },
            {
                "name": "Cost Calculator",
                "description": "Calculate formulation costs and pricing"
            },
            {
                "name": "Ingredient Search",
                "description": "Search and retrieve ingredient information from databases"
            },
            {
                "name": "Formula Generation",
                "description": "AI-powered formula generation based on requirements"
            },
            {
                "name": "Inspiration Boards",
                "description": "Manage inspiration boards and product collections"
            },
            {
                "name": "Face Analysis",
                "description": "Facial analysis and skin condition assessment endpoints"
            },
            {
                "name": "HL Alerts",
                "description": "Hyperlocal skin alert engine endpoints"
            },
            {
                "name": "Authentication",
                "description": "JWT-based authentication and user management"
            },
            {
                "name": "Dashboard",
                "description": "Dashboard statistics and analytics endpoints"
            },
            {
                "name": "Trend Insights",
                "description": "Real-time market intelligence and trend analysis using SerpAPI"
            },
            {
                "name": "Make a Wish",
                "description": "Feature request and wishlist management"
            }
        ]
    )
    
    # OpenAPI servers: only SERVER_URL from env (no hardcoded API bases)
    if server_url:
        openapi_schema["servers"] = [
            {
                "url": server_url,
                "description": "Production server"
                if node_env == "production"
                else "Development server",
            },
        ]
    else:
        openapi_schema["servers"] = [
            {
                "url": "/",
                "description": "Relative to this host — set SERVER_URL for a fixed base URL in Swagger.",
            },
        ]
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token authentication. Include the token in the Authorization header as: Bearer <token>"
        }
    }
    
    # Set default security (optional - can be overridden per route)
    # Note: This makes all endpoints require authentication by default in the docs
    # Individual routes can opt out by not using the security dependency
    openapi_schema["security"] = [
        {
            "bearerAuth": []
        }
    ]
    
    # Add external documentation
    openapi_schema["externalDocs"] = {
        "description": "SkinBB API Documentation",
        "url": "https://www.formulynx.in/api-docs"
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Override the default OpenAPI function
app.openapi = custom_openapi

# ✅ CORS - Configuration loaded from .env
# Parse CORS settings from environment variables
cors_allow_origins_str = os.getenv("CORS_ALLOW_ORIGINS", "")
cors_allow_origins = [origin.strip() for origin in cors_allow_origins_str.split(",") if origin.strip()] if cors_allow_origins_str else []

cors_allow_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX", None)

cors_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

cors_allow_methods_str = os.getenv("CORS_ALLOW_METHODS", "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD")
cors_allow_methods = [method.strip() for method in cors_allow_methods_str.split(",") if method.strip()] if cors_allow_methods_str else ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

cors_allow_headers_str = os.getenv("CORS_ALLOW_HEADERS", "*")
cors_allow_headers = ["*"] if cors_allow_headers_str.strip() == "*" else [header.strip() for header in cors_allow_headers_str.split(",") if header.strip()]

cors_expose_headers_str = os.getenv("CORS_EXPOSE_HEADERS", "*")
cors_expose_headers = ["*"] if cors_expose_headers_str.strip() == "*" else [header.strip() for header in cors_expose_headers_str.split(",") if header.strip()]

cors_max_age = int(os.getenv("CORS_MAX_AGE", "3600"))

# This middleware handles all CORS preflight (OPTIONS) and actual requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=cors_allow_origin_regex,
    allow_credentials=cors_allow_credentials,
    allow_methods=cors_allow_methods,
    allow_headers=cors_allow_headers,
    expose_headers=cors_expose_headers,
    max_age=cors_max_age,  # Cache preflight requests
)

# ✅ Existing chatbot API
if api_router is not None:
    app.include_router(api_router, prefix="/api")
else:
    print("Warning: Chatbot router not available, skipping registration")

# ✅ Add analyze-inci API
app.include_router(analyze_inci_router, prefix="/api")   # <--- added

# ✅ Add formulation report API
if formulation_report_router is not None:
    app.include_router(formulation_report_router, prefix="/api")
else:
    print("Warning: Formulation Report router not available, skipping registration")

# ✅ Add cost calculator API
app.include_router(cost_calculator_router, prefix="/api")

# ✅ Add ingredient search API
app.include_router(ingredient_search_router, prefix="/api")

# ✅ Add market research API
app.include_router(market_research_router, prefix="/api")

# ✅ Add distributor management API
app.include_router(distributor_management_router, prefix="/api")

# ✅ Add ingredient costs CRUD API
app.include_router(ingredient_costs_router, prefix="/api")

# ✅ Add ingredient history API
app.include_router(ingredient_history_router, prefix="/api")

# ✅ Add product comparison API
app.include_router(product_comparison_router, prefix="/api")

# ✅ Add health checks API
app.include_router(health_checks_router, prefix="/api")

# ✅ Add HLHP engine API
app.include_router(hl_alerts_router, prefix="/api")
app.include_router(hl_personalized_alerts_router, prefix="/api")
app.include_router(hlhp_scan_router, prefix="/api")
app.include_router(hlhp_composition_router, prefix="/api")
app.include_router(hlhp_weather_router, prefix="/api")

# ✅ Add trend insights API
if trend_insights_router is not None:
    app.include_router(trend_insights_router, prefix="/api")
else:
    print("Warning: Trend Insights router not available, skipping registration")

# ✅ Add formula generation API
if formula_generation_router is not None:
    app.include_router(formula_generation_router, prefix="/api")
else:
    print("Warning: Formula Generation router not available, skipping registration")

# ✅ Add Make a Wish API (Consolidated - includes all endpoints)
if make_wish_router is not None:
    app.include_router(make_wish_router, prefix="/api")
    print("✅ Make a Wish API router registered successfully")
else:
    print("Warning: Make a Wish router not available, skipping registration")

# ✅ Add Notifications API
if notifications_router is not None:
    app.include_router(notifications_router, prefix="/api")
else:
    print("Warning: Notifications router not available, skipping registration")

# ✅ Add WebSocket Routes for Real-time Notifications
try:
    from app.ai_ingredient_intelligence.api.websocket_routes import router as websocket_router
    app.include_router(websocket_router, prefix="/api")
    print("✅ WebSocket routes registered")
except ImportError as e:
    print(f"Warning: Could not import websocket routes: {e}")
    print("   WebSocket notifications will not be available.")

# ✅ Add Inspiration Boards API
try:
    from app.ai_ingredient_intelligence.api.inspiration_boards import router as inspiration_boards_router
    app.include_router(inspiration_boards_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import inspiration_boards router: {e}")
    print("   Inspiration Boards API will not be available. This is not critical.")

# ✅ Add Dashboard Stats API
try:
    from app.ai_ingredient_intelligence.api.dashboard_stats import router as dashboard_stats_router
    app.include_router(dashboard_stats_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import dashboard_stats router: {e}")
    print("   Dashboard Stats API will not be available. This is not critical.")

# ✅ Add Authentication API (JWT login, refresh, etc.)
try:
    from app.ai_ingredient_intelligence.auth import auth_router
    app.include_router(auth_router, prefix="/api")
except ImportError as e:
    print(f"Warning: Could not import auth router: {e}")
    print("   Authentication API will not be available.")

# ✅ Add QMS (Query Management System) API
try:
    from app.ai_ingredient_intelligence.api.qms_routes import router as qms_router
    app.include_router(qms_router, prefix="/api")
    print("✅ QMS router registered successfully")
except ImportError as e:
    print(f"Warning: Could not import QMS router: {e}")
    print("   QMS API will not be available.")

# ✅ Credits API: Using third-party API via CREDITS_API_BASE_URL (paths in credit_service.py)
# credit_service.py handles all credit deduction calls to external API

# ✅ New image-to-JSON API - Commented out - module doesn't exist
# app.include_router(image_extractor_router, prefix="/api")

# ✅ Face Analysis API - Include router instead of mounting
if face_analysis_router is not None:
    app.include_router(face_analysis_router, prefix="/api/face-analysis", tags=["Face Analysis"])
else:
    print("Warning: Face Analysis router not available, skipping registration")

@app.on_event("startup")
async def create_indexes():
    """Create indexes for MongoDB collections on startup"""
    try:
        # Create indexes for distributor collection
        await distributor_col.create_index("ingredientName")
        await distributor_col.create_index("createdAt")
        await distributor_col.create_index([("ingredientName", 1), ("createdAt", -1)])
        print("Distributor collection indexes created successfully")
        
        # Create indexes for decode history collection
        from app.ai_ingredient_intelligence.db.collections import decode_history_col, compare_history_col
        await decode_history_col.create_index("user_id")
        await decode_history_col.create_index("created_at")
        await decode_history_col.create_index([("user_id", 1), ("created_at", -1)])
        await decode_history_col.create_index([("user_id", 1), ("name", "text")])
        print("Decode history collection indexes created successfully")
        
        # Create indexes for compare history collection
        await compare_history_col.create_index("user_id")
        await compare_history_col.create_index("created_at")
        await compare_history_col.create_index([("user_id", 1), ("created_at", -1)])
        await compare_history_col.create_index([("user_id", 1), ("name", "text")])
        print("Compare history collection indexes created successfully")
        
        # Create indexes for inspiration boards collections
        from app.ai_ingredient_intelligence.db.collections import (
            inspiration_boards_col, inspiration_products_col
        )
        await inspiration_boards_col.create_index("user_id")
        await inspiration_boards_col.create_index("created_at")
        await inspiration_boards_col.create_index([("user_id", 1), ("created_at", -1)])
        await inspiration_products_col.create_index("board_id")
        await inspiration_products_col.create_index("user_id")
        await inspiration_products_col.create_index([("board_id", 1), ("decoded", 1)])
        await inspiration_products_col.create_index([("user_id", 1), ("created_at", -1)])
        print("Inspiration boards collection indexes created successfully")
        
        # Create indexes for formulynx_notifications collection
        from app.ai_ingredient_intelligence.db.collections import notifications_col
        await notifications_col.create_index("user_id")
        await notifications_col.create_index("createdAt")
        await notifications_col.create_index([("user_id", 1), ("createdAt", -1)])
        await notifications_col.create_index([("user_id", 1), ("read", 1)])
        await notifications_col.create_index([("user_id", 1), ("module", 1)])
        await notifications_col.create_index("id", unique=True)
        print("Formulynx notifications collection indexes created successfully")

        from app.hlhp.mongo_setup import ensure_hlhp_indexes

        await ensure_hlhp_indexes()
        print("HLHP Mongo indexes ensured")
    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")
        # Don't fail startup if indexes already exist

@app.get("/")
async def root():
    return {"message": "Welcome to SkinBB AI Chatbot API. Use POST /api/chat to interact v1."}

@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy", 
        "message": "Server is running",
        "endpoints": {
            "api_docs": "/docs",
            "server_health": "/api/server-health",
            "test_selenium": "/api/test-selenium"
        }
    }
