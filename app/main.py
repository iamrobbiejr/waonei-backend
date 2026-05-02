import os
import uuid
from typing import Optional
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from supabase import create_client, Client
from pydantic import BaseModel, Field, EmailStr
from app.loggerConfig import setup_logging


# Import the task
from app.worker import celery_app
from app.tasks import process_violation

# Initialize logger - CALL THE FUNCTION HERE
logger = setup_logging()

load_dotenv()

tags_metadata = [
    {
        "name": "Authentication",
        "description": "Operations to authenticate users.",
    },
    {
        "name": "Reports",
        "description": "Manage traffic violation reports.",
    },
    {
        "name": "Admin",
        "description": "Admin-only operations.",
    },
    {
        "name": "Statistics",
        "description": "Get global statistics about violations.",
    },
    {
        "name": "Health",
        "description": "Health check endpoint.",
    },
]

app = FastAPI(
    title="WAONEI Traffic Violation Reporter",
    description="Anonymous traffic violation reporting with AI verification",
    version="2.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",      # Explicitly set
    redoc_url="/redoc",    # Explicitly set
    openapi_url="/openapi.json"
)

# Allow Frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000", # Add the backend itself
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init Supabase
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)


# Pydantic Models for Request/Response
class ReportResponse(BaseModel):
    """Response model for report submission"""
    status: str
    message: str
    report_id: str
    task_id: Optional[str] = None


class ReportStatusResponse(BaseModel):
    """Response model for report status"""
    success: bool
    report: dict


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"  # The default role is user, can be overridden by admin


class UserResponse(BaseModel):
    id: str
    email: str
    role: str = "user"
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Security
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the JWT token and return the user."""
    token = credentials.credentials
    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user.user
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def check_admin(user=Depends(get_current_user)):
    """Check if the current user has admin privileges."""
    # In a real-world scenario, you might store roles in user_metadata or a separate table.
    # For this implementation, we'll check the user_metadata for a 'role' field.
    user_role = user.user_metadata.get('role', 'user') if user.user_metadata else 'user'
    
    if user_role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user


# Helper function to get client IP
def get_client_ip(request: Request) -> str:
    """Extract client IP address"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/", tags=["Health"])
async def root():
    """API root endpoint"""
    return {
        "app": "WAONEI Traffic Violation Reporter",
        "version": "2.0.0",
        "status": "active",
        "endpoints": {
            "submit_report": "/report",
            "get_report": "/report/{report_id}",
            "get_violations": "/violations",
            "get_pending_violations": "/pending-violations",
            "get_stats": "/statistics",
            "health": "/health",
            "login": "/auth/login",
            "create_user": "/admin/users"
        }
    }


@app.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
async def login(user_data: UserLogin):
    """
    Login endpoint to get an access token.
    """
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })

        if not auth_response.user or not auth_response.session:
             raise HTTPException(status_code=400, detail="Invalid login credentials")
        
        user = auth_response.user
        role = user.user_metadata.get('role', 'user') if user.user_metadata else 'user'

        return LoginResponse(
            access_token=auth_response.session.access_token,
            user=UserResponse(
                id=user.id,
                email=user.email,
                role=role,
                created_at=user.created_at
            )
        )
    except Exception as e:
        logger.error(f"Login failed for {user_data.email}: {str(e)}")
        raise HTTPException(status_code=400, detail="Start Login Failed or Invalid credentials")


@app.post("/admin/users", response_model=UserResponse, tags=["Admin"])
async def create_user(
    new_user: UserCreate, 
    current_user=Depends(check_admin)
):
    """
    Create a new user (admin only).
    """
    try:
        # Create user using Supabase Admin API (requires service_role key)
        attributes = {
            "email": new_user.email,
            "password": new_user.password,
            "email_confirm": True,
            "user_metadata": {"role": new_user.role}
        }
        
        # Use the admin client (supabase variable is init with service role key)
        user_response = supabase.auth.admin.create_user(attributes)
        
        if not user_response: # Check if user is actually created
             raise HTTPException(status_code=400, detail="Failed to create user")
        
        user = user_response.user
        
        logger.info(f"Admin {current_user.email} created new user {user.email} with role {new_user.role}")
        
        return UserResponse(
            id=user.id,
            email=user.email,
            role=new_user.role,
            created_at=user.created_at or datetime.now(timezone.utc).isoformat()
        )
            
    except Exception as e:
        logger.error(f"User creation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to create user: {str(e)}")


@app.post("/report", response_model=ReportResponse, tags=["Reports"])
async def create_report(
        request: Request,
        file: UploadFile = File(..., description="Image or video evidence"),
        latitude: Optional[float] = Form(None, description="GPS latitude"),
        longitude: Optional[float] = Form(None, description="GPS longitude"),
        location_description: Optional[str] = Form(None, description="Location description"),
        violation_type: Optional[str] = Form(None, description="Reported violation type"),
        description: Optional[str] = Form(None, description="Additional details"),
        vehicle_plate: Optional[str] = Form(None, description="Vehicle plate number"),
        vehicle_color: Optional[str] = Form(None, description="Vehicle color"),
        vehicle_make: Optional[str] = Form(None, description="Vehicle make/model"),
):
    """
    Submit a new traffic violation report
    """
    reporter_ip = get_client_ip(request)

    # Log incoming request
    logger.info(
        f"New report submission - IP: {reporter_ip}, "
        f"File: {file.filename}, Content-Type: {file.content_type}, "
        f"Violation: {violation_type or 'not_specified'}"
    )

    try:
        # Validate file type
        allowed_types = [
            'image/jpeg', 'image/jpg', 'image/png',
            'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm'
        ]
        if file.content_type not in allowed_types:
            logger.warning(
                f"Invalid file type rejected - IP: {reporter_ip}, "
                f"Type: {file.content_type}, File: {file.filename}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
            )

        # Validate file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        max_size = 100 * 1024 * 1024  # 100MB
        if file_size > max_size:
            logger.warning(
                f"File size exceeded - IP: {reporter_ip}, "
                f"Size: {file_size / (1024 * 1024):.2f}MB, Max: 20MB"
            )
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: 20MB"
            )

        logger.info(f"File validation passed - Size: {file_size / (1024 * 1024):.2f}MB")

        # 1. Generate unique ID for file
        file_ext = file.filename.split(".")[-1]
        file_name = f"{uuid.uuid4()}.{file_ext}"

        # 2. Upload to Supabase Storage
        logger.info(f"Uploading file to Supabase - Name: {file_name}")
        file_content = await file.read()
        bucket_name = "evidence-uploads"

        try:
            res = supabase.storage.from_(bucket_name).upload(
                file_name,
                file_content,
                file_options={
                    "content-type": file.content_type,
                    "cache-control": "3600"
                }
            )
            logger.info(f"File uploaded successfully - Bucket: {bucket_name}, File: {file_name}")
        except Exception as e:
            logger.error(f"Supabase upload failed - File: {file_name}, Error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to upload file to storage"
            )

        # Get Public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        logger.debug(f"Public URL generated: {public_url}")

        # 3. Prepare vehicle details JSONB
        vehicle_details = None
        if vehicle_plate or vehicle_color or vehicle_make:
            vehicle_details = {
                "plate_number": vehicle_plate,
                "color": vehicle_color,
                "make": vehicle_make
            }
            logger.debug(f"Vehicle details captured: {vehicle_details}")

        # Get reporter info
        reporter_user_agent = request.headers.get("User-Agent", "unknown")

        # 4. Create Database Entry
        logger.info("Creating database entry")
        data = {
            "file_url": public_url,
            "file_name": file_name,
            "file_type": file.content_type,
            "file_size": file_size,
            "status": "pending_analysis",
            "violation_type": "unknown",
            "reported_violation_type": violation_type or "not_specified",
            "confidence_score": 0.0,
            "latitude": latitude,
            "longitude": longitude,
            "location_description": location_description,
            "description": description,
            "vehicle_details": vehicle_details,
            "reporter_ip": reporter_ip,
            "reporter_user_agent": reporter_user_agent,
            "metadata": {
                "original_filename": file.filename,
                "upload_timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

        try:
            db_res = supabase.table("reports").insert(data).execute()

            if not db_res.data:
                logger.error("Database insert returned empty data")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create report in database"
                )

            report_id = db_res.data[0]['id']
            logger.info(
                f"Report created successfully - ID: {report_id}, "
                f"File: {file_name}, IP: {reporter_ip}"
            )
        except Exception as e:
            logger.error(f"Database insert failed - Error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to save report to database"
            )

        # 5. Trigger Background Worker for AI Analysis
        logger.info(f"Triggering AI analysis - Report ID: {report_id}")
        try:
            task = process_violation.delay(report_id, public_url)
            logger.info(
                f"AI analysis task queued - Report ID: {report_id}, "
                f"Task ID: {task.id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to queue AI analysis task - Report ID: {report_id}, "
                f"Error: {str(e)}"
            )
            # Don't fail the request, report is already saved
            task_id = None
        else:
            task_id = task.id

        response = ReportResponse(
            status="success",
            message="Report received and queued for AI analysis",
            report_id=report_id,
            task_id=task_id
        )

        logger.info(
            f"Request completed successfully - Report ID: {report_id}, "
            f"Task ID: {task_id}"
        )

        return response

    except HTTPException as he:
        # Log HTTP exceptions (validation errors, etc.)
        logger.warning(
            f"Request validation failed - IP: {reporter_ip}, "
            f"Status: {he.status_code}, Detail: {he.detail}"
        )
        raise
    except Exception as e:
        # Log unexpected errors
        logger.error(
            f"Unexpected error processing report - IP: {reporter_ip}, "
            f"File: {file.filename}, Error: {str(e)}",
            exc_info=True  # This includes the full stack trace
        )
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@app.get("/report/{report_id}", response_model=ReportStatusResponse, tags=["Reports"])
async def get_report(report_id: str):
    """
    Get the status and details of a specific report
    """
    try:
        result = supabase.table("reports") \
            .select("*") \
            .eq("id", report_id) \
            .single() \
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Report not found")

        return ReportStatusResponse(
            success=True,
            report=result.data
        )

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Report not found")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/violations", tags=["Reports"])
async def get_violations(
        limit: int = 50,
        offset: int = 0,
        violation_type: Optional[str] = None,
        status: str = "verified",
        min_confidence: float = 0.0
):
    """
    Get list of violations by status (verified or no_violation)

    - **limit**: Number of results (max 100)
    - **offset**: Pagination offset
    - **violation_type**: Filter by type (no_helmet, red_light, wrong_way, illegal_parking)
    - **status**: Filter by status (verified or no_violation, defaults to verified)
    - **min_confidence**: Minimum confidence score (defaults to 0.0)
    """
    try:
        limit = min(limit, 100)

        query = supabase.table("reports") \
            .select("*") \
            .eq("status", status) \
            .gte("confidence_score", min_confidence) \
            .order("created_at", desc=True) \
            .range(offset, offset + limit - 1)

        if violation_type and violation_type != "all":
            query = query.eq("violation_type", violation_type)

        result = query.execute()

        return {
            "success": True,
            "count": len(result.data),
            "violations": result.data,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(result.data) == limit
            }
        }

    except Exception as e:
        logger.error(f"Error fetching verified violations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pending-violations", tags=["Reports"])
async def get_pending_violations(
        limit: int = 50,
        offset: int = 0,
        violation_type: Optional[str] = None,
        min_confidence: float = 0.0,
        status: str = "pending_analysis"
):
    """
    Get list of reports not yet verified (pending analysis)

    - **limit**: Number of results (max 100)
    - **offset**: Pagination offset
    - **violation_type**: Filter by type
    - **min_confidence**: Minimum confidence score
    - **status**: Report status (pending_analysis, rejected, failed)
    """
    try:
        limit = min(limit, 100)

        # Ensure we don't return verified reports here
        if status == "verified":
             status = "pending_analysis"

        query = supabase.table("reports") \
            .select("*") \
            .eq("status", status) \
            .gte("confidence_score", min_confidence) \
            .order("created_at", desc=True) \
            .range(offset, offset + limit - 1)

        if violation_type and violation_type != "all":
            query = query.eq("violation_type", violation_type)

        result = query.execute()

        return {
            "success": True,
            "count": len(result.data),
            "violations": result.data,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(result.data) == limit
            }
        }

    except Exception as e:
        logger.error(f"Error fetching pending violations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/statistics", tags=["Statistics"])
async def get_statistics():
    """
    Get overall violation statistics
    """
    try:
        # Get counts by violation type
        all_reports = supabase.table("reports").select("*").execute()

        stats = {
            "total_reports": len(all_reports.data),
            "by_status": {},
            "by_violation_type": {},
            "average_confidence": 0.0,
            "recent_24h": 0
        }

        # Calculate stats
        verified_scores = []
        now = datetime.now(timezone.utc)

        for report in all_reports.data:
            # Status counts
            status = report.get('status', 'unknown')
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            # Violation type counts
            v_type = report.get('violation_type', 'unknown')
            stats['by_violation_type'][v_type] = stats['by_violation_type'].get(v_type, 0) + 1

            # Average confidence for verified
            if status == 'verified' and report.get('confidence_score'):
                verified_scores.append(report['confidence_score'])

            # Recent 24h count
            created_at = datetime.fromisoformat(report['created_at'].replace('Z', '+00:00'))
            if (now - created_at).total_seconds() < 86400:
                stats['recent_24h'] += 1

        if verified_scores:
            stats['average_confidence'] = sum(verified_scores) / len(verified_scores)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        supabase.table("reports").select("count").limit(1).execute()

        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": "connected",
            "storage": "connected"
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)