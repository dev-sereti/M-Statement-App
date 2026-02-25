"""API route handlers for upload, process, and download."""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

import aiofiles
from fastapi import (
    APIRouter, UploadFile, File, HTTPException,
    BackgroundTasks, Request,
)
from fastapi.responses import FileResponse

from app.config import settings
from app.security import (
    RateLimiter, PinAttemptTracker,
    generate_session_id, secure_filename, hash_file_content,
)
from app.services.pdf_processor import SecurePDFProcessor
from app.services.statement_parser import MPesaStatementParser
from app.services.excel_generator import MPesaExcelGenerator
from app.models.schemas import (
    UploadResponse, ProcessRequest, ProcessResponse, HealthResponse,
)
from app.api.middleware import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Service instances
pdf_processor = SecurePDFProcessor()
parser = MPesaStatementParser()
excel_generator = MPesaExcelGenerator()

# Security instances
rate_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_PER_MINUTE)
pin_tracker = PinAttemptTracker(max_attempts=settings.MAX_PIN_ATTEMPTS)

# In-memory session store (use Redis in production)
sessions: Dict[str, dict] = {}


# ─── Health ────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
    )


# ─── Upload ───────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload a PDF statement. Returns session ID."""
    client_ip = get_client_ip(request)

    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Validate filename
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read content
    content = await file.read()

    # Size check
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum {settings.MAX_FILE_SIZE_MB}MB",
        )

    if len(content) < 100:
        raise HTTPException(status_code=400, detail="File appears empty or corrupt")

    # Validate PDF structure
    is_valid, message, is_encrypted = pdf_processor.validate_pdf(content)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    # Create session
    session_id = generate_session_id()
    safe_name = secure_filename(file.filename)
    file_hash = hash_file_content(content)

    sessions[session_id] = {
        "file_content": content,
        "filename": safe_name,
        "file_hash": file_hash,
        "is_encrypted": is_encrypted,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow()
        + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES),
        "processed": False,
        "output_path": None,
        "download_token": None,
        "transaction_count": 0,
        "client_ip": client_ip,
    }

    # Schedule cleanup
    background_tasks.add_task(
        cleanup_session, session_id, settings.SESSION_EXPIRE_MINUTES
    )

    logger.info(
        f"Upload OK: session={session_id[:8]}... "
        f"encrypted={is_encrypted} size={len(content)}"
    )

    return UploadResponse(
        session_id=session_id,
        filename=safe_name,
        is_encrypted=is_encrypted,
        file_size_kb=round(len(content) / 1024, 2),
        message=(
            "File uploaded. Please provide your PIN to process."
            if is_encrypted
            else "File uploaded. Ready to process."
        ),
    )


# ─── Process ──────────────────────────────────────────────────

@router.post("/process", response_model=ProcessResponse)
async def process_statement(
    request: Request,
    process_request: ProcessRequest,
):
    """Decrypt PDF, extract transactions, generate Excel."""
    client_ip = get_client_ip(request)
    session_id = process_request.session_id

    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Validate session
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload again.",
        )

    if datetime.utcnow() > session["expires_at"]:
        sessions.pop(session_id, None)
        raise HTTPException(status_code=410, detail="Session expired")

    # Already processed?
    if session.get("processed") and session.get("download_token"):
        return ProcessResponse(
            success=True,
            download_token=session["download_token"],
            transaction_count=session.get("transaction_count", 0),
            parsing_warnings=[],
            message="Already processed. Download your file.",
        )

    # ── PIN handling ────────────────────────────────────────────
    if session["is_encrypted"]:
        if not process_request.pin:
            raise HTTPException(status_code=400, detail="PIN is required")

        # Check lockout first
        pre_check = pin_tracker.check_and_record(session_id, False)
        if pre_check.get("locked"):
            raise HTTPException(
                status_code=423,
                detail=(
                    f"Too many failed attempts. "
                    f"Try again in {pre_check['remaining_seconds']}s"
                ),
            )
        # Undo the failed record we just added for the pre-check
        pin_tracker._attempts[session_id]["count"] -= 1

        result = pdf_processor.decrypt_and_extract(
            session["file_content"], process_request.pin
        )

        if not result.success:
            attempt_status = pin_tracker.check_and_record(session_id, False)
            detail = result.error or "Processing failed"
            if attempt_status.get("locked"):
                raise HTTPException(
                    status_code=423,
                    detail=(
                        f"Too many failed attempts. "
                        f"Try again in {attempt_status['remaining_seconds']}s"
                    ),
                )
            if attempt_status.get("attempts_left", 0) > 0:
                detail += f" ({attempt_status['attempts_left']} attempts left)"
            raise HTTPException(status_code=401, detail=detail)

        pin_tracker.check_and_record(session_id, True)

    else:
        result = pdf_processor.decrypt_and_extract(session["file_content"], "")
        if not result.success:
            raise HTTPException(
                status_code=422,
                detail=result.error or "Could not process PDF",
            )

    # ── Parse transactions ──────────────────────────────────────
    try:
        parsed = parser.parse(result.text_content)
    except Exception as e:
        logger.error(f"Parser error: {e}")
        raise HTTPException(status_code=422, detail="Could not parse statement")

    if not parsed.transactions:
        raise HTTPException(
            status_code=422,
            detail="No transactions found in the statement.",
        )

    # ── Generate Excel ──────────────────────────────────────────
    try:
        excel_bytes = excel_generator.generate(parsed)
    except Exception as e:
        logger.error(f"Excel error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate Excel")

    download_token = generate_session_id()
    output_filename = f"mpesa_statement_{download_token[:8]}.xlsx"
    output_path = settings.OUTPUT_DIR / output_filename

    async with aiofiles.open(output_path, "wb") as f:
        await f.write(excel_bytes)

    # Update session
    session["processed"] = True
    session["output_path"] = str(output_path)
    session["download_token"] = download_token
    session["transaction_count"] = len(parsed.transactions)
    session["file_content"] = None  # Free memory

    logger.info(
        f"Processed: session={session_id[:8]}... "
        f"transactions={len(parsed.transactions)}"
    )

    return ProcessResponse(
        success=True,
        download_token=download_token,
        transaction_count=len(parsed.transactions),
        parsing_warnings=parsed.parsing_warnings[:10],
        account_name=parsed.metadata.account_name,
        message=f"Extracted {len(parsed.transactions)} transactions.",
    )


# ─── Download ─────────────────────────────────────────────────

@router.get("/download/{download_token}")
async def download_excel(
    request: Request,
    download_token: str,
    background_tasks: BackgroundTasks,
):
    """Download the generated Excel file."""
    client_ip = get_client_ip(request)

    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Find matching session
    matching_session = None
    for session in sessions.values():
        if session.get("download_token") == download_token:
            matching_session = session
            break

    if not matching_session:
        raise HTTPException(status_code=404, detail="Download not found or expired")

    output_path = Path(matching_session["output_path"])
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="File no longer available")

    safe_name = f"MPesa_Statement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    background_tasks.add_task(delete_file_after_delay, str(output_path), 120)

    return FileResponse(
        path=str(output_path),
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


# ─── Background Tasks ─────────────────────────────────────────

async def cleanup_session(session_id: str, delay_minutes: int) -> None:
    """Remove session and associated files after delay."""
    await asyncio.sleep(delay_minutes * 60)
    session = sessions.pop(session_id, None)
    if session:
        if session.get("output_path"):
            path = Path(session["output_path"])
            if path.exists():
                path.unlink()
        logger.info(f"Session {session_id[:8]}... cleaned up")


async def delete_file_after_delay(file_path: str, delay_seconds: int) -> None:
    """Delete a file after a delay."""
    await asyncio.sleep(delay_seconds)
    path = Path(file_path)
    if path.exists():
        path.unlink()
        logger.info(f"Deleted file: {path.name}")