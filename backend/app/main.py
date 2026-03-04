"""FastAPI Application Factory"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from app.config import settings
from app.api.v1 import auth, journals, admin, author, editor, reviewer, articles, roles, webhooks, copyright
from app.core.rate_limit import limiter, get_rate_limit_key
from app.scheduler.tasks import start_scheduler, shutdown_scheduler
from app.db.database import engine, Base, SessionLocal
from app.db import models  # Import models to register them with Base
from app.db.models import User
from app.core.auth import hash_password

logger = logging.getLogger(__name__)
scheduler = None


def run_migrations():
    """Run database migrations for schema updates on existing tables"""
    print("Running database migrations...")
    
    with engine.connect() as conn:
        try:
            # Migration: Add title_page and blinded_manuscript columns to papers table
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'title_page'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN title_page VARCHAR(200) DEFAULT '' AFTER file"))
                print("Migration: Added 'title_page' column to paper table")
            
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'blinded_manuscript'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN blinded_manuscript VARCHAR(200) DEFAULT '' AFTER title_page"))
                print("Migration: Added 'blinded_manuscript' column to paper table")
            
            # Migration: Add revision files columns (for resubmission)
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'revised_track_changes'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN revised_track_changes VARCHAR(200) DEFAULT '' AFTER blinded_manuscript"))
                print("Migration: Added 'revised_track_changes' column to paper table")
            
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'revised_clean'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN revised_clean VARCHAR(200) DEFAULT '' AFTER revised_track_changes"))
                print("Migration: Added 'revised_clean' column to paper table")
            
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'response_to_reviewer'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN response_to_reviewer VARCHAR(200) DEFAULT '' AFTER revised_clean"))
                print("Migration: Added 'response_to_reviewer' column to paper table")
            
            # Migration: Increase abstract column size to 2500 characters
            result = conn.execute(text("SHOW COLUMNS FROM paper WHERE Field = 'abstract'"))
            col_info = result.fetchone()
            if col_info and 'varchar(1500)' in str(col_info).lower():
                conn.execute(text("ALTER TABLE paper MODIFY COLUMN abstract VARCHAR(2500) NOT NULL DEFAULT ''"))
                print("Migration: Increased 'abstract' column size to 2500 characters")
            
            # Migration: Add is_external column to reviewer_invitation table
            try:
                result = conn.execute(text("SHOW COLUMNS FROM reviewer_invitation LIKE 'is_external'"))
                if not result.fetchone():
                    conn.execute(text("ALTER TABLE reviewer_invitation ADD COLUMN is_external TINYINT(1) DEFAULT 0"))
                    print("Migration: Added 'is_external' column to reviewer_invitation table")
            except Exception:
                pass  # Table may not exist yet
            
            # Migration: Add paper_type column to paper table
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'paper_type'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN paper_type VARCHAR(50) DEFAULT 'Full Length Article'"))
                print("Migration: Added 'paper_type' column to paper table")
            
            # Migration: Add co_authors_json column to paper_published table
            try:
                result = conn.execute(text("SHOW COLUMNS FROM paper_published LIKE 'co_authors_json'"))
                if not result.fetchone():
                    conn.execute(text("ALTER TABLE paper_published ADD COLUMN co_authors_json TEXT NULL"))
                    print("Migration: Added 'co_authors_json' column to paper_published table")
            except Exception:
                pass  # Table may not exist yet
            
            # Migration: Add accepted_on column to paper table
            result = conn.execute(text("SHOW COLUMNS FROM paper LIKE 'accepted_on'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE paper ADD COLUMN accepted_on DATETIME NULL"))
                print("Migration: Added 'accepted_on' column to paper table")
            
            conn.commit()
            print("Database migrations completed successfully")
            
        except Exception as e:
            # Table might not exist yet (first run) - that's OK, create_all will handle it
            print(f"Migration check: {str(e)}")


def create_admin_user():
    """Create default admin user if it doesn't exist"""
    db = SessionLocal()
    try:
        # Check if admin user exists
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@aacsjournals.com")
        existing_admin = db.query(User).filter(User.email == admin_email).first()
        
        if not existing_admin:
            admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
            admin_user = User(
                email=admin_email,
                password=hash_password(admin_password),
                role="Admin",
                fname="Admin",
                lname="User",
            )
            db.add(admin_user)
            db.commit()
            print(f"Admin user created: {admin_email}")
        else:
            print(f"Admin user already exists: {admin_email}")
    except Exception as e:
        print(f"Failed to create admin user: {str(e)}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app startup and shutdown events"""
    global scheduler
    
    # Create database tables if they don't exist
    print("Creating database tables if needed...")
    try:
        # Import all models to ensure they're registered with Base
        from app.db import models as db_models
        tables = list(Base.metadata.tables.keys())
        print(f"Registered tables: {tables}")
        
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
        
        # Run any pending migrations for schema updates
        run_migrations()
        
        # Create admin user
        create_admin_user()
    except Exception as e:
        print(f"Failed to create database tables: {str(e)}")
        import traceback
        print(traceback.format_exc())
    
    # Startup: Start the scheduler
    print("Starting application with scheduler...")
    try:
        scheduler = start_scheduler()
    except Exception as e:
        print(f"Failed to initialize scheduler: {str(e)}")
    
    yield
    
    # Shutdown: Stop the scheduler
    print("Shutting down application...")
    shutdown_scheduler(scheduler)


# Create FastAPI application with lifespan
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add trusted host middleware (runs third)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.aacsjournals.com", "*.railway.app", "*.up.railway.app", "*.vercel.app"]
)

# Add rate limiting middleware (runs second)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Custom rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "error": "rate_limit_exceeded"
        }
    )

# Add CORS middleware LAST so it runs FIRST (handles OPTIONS preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        Status of the API
    """
    return {
        "status": "healthy",
        "service": "Breakthrough Publishers India Backend API",
        "version": settings.API_VERSION
    }


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint providing API information.
    
    Returns:
        API information and available endpoints
    """
    return {
        "name": settings.API_TITLE,
        "description": settings.API_DESCRIPTION,
        "version": settings.API_VERSION,
        "documentation": "/docs",
        "endpoints": {
            "health": "/health",
            "auth": "/api/v1/auth/login",
            "documentation": "/docs"
        }
    }


# Include routers
app.include_router(auth.router)
app.include_router(journals.router)
app.include_router(articles.router)
app.include_router(admin.router)
app.include_router(author.router)
app.include_router(editor.router)
app.include_router(reviewer.router)
app.include_router(roles.router)
app.include_router(webhooks.router)
app.include_router(copyright.router)


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": str(type(exc).__name__)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        reload_excludes=["venv", "__pycache__", "*.pyc", ".git"]
    )
