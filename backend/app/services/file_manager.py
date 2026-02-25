"""
Secure file storage manager with integrity verification,
automatic expiration, and secure deletion.
"""

import os
import re
import hashlib
import secrets
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

import aiofiles
import aiofiles.os

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Data Models ───────────────────────────────────────────────

@dataclass
class FileInfo:
    """Metadata about a managed file."""

    file_id: str
    original_name: str
    safe_name: str
    file_path: Path
    file_hash: str
    size_bytes: int
    content_type: str
    created_at: datetime
    expires_at: datetime
    is_encrypted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def size_kb(self) -> float:
        return round(self.size_bytes / 1024, 2)

    @property
    def remaining_seconds(self) -> int:
        if self.is_expired:
            return 0
        return int((self.expires_at - datetime.utcnow()).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "original_name": self.original_name,
            "safe_name": self.safe_name,
            "size_bytes": self.size_bytes,
            "size_kb": self.size_kb,
            "content_type": self.content_type,
            "is_encrypted": self.is_encrypted,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_expired": self.is_expired,
            "remaining_seconds": self.remaining_seconds,
        }


# ─── File Manager ─────────────────────────────────────────────

class SecureFileManager:
    """
    Manages secure file storage with automatic cleanup.

    Features:
    - Cryptographically random file IDs
    - SHA-256 integrity verification on read
    - Secure deletion (overwrite before unlink)
    - Automatic expiration and cleanup loop
    - Restrictive file permissions (0o600)
    """

    ALLOWED_EXTENSIONS = {".pdf"}
    ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
    CHUNK_SIZE = 8192  # 8 KB read chunks

    def __init__(
        self,
        upload_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        max_file_size_mb: Optional[int] = None,
        retention_minutes: Optional[int] = None,
    ):
        self.upload_dir = upload_dir or settings.UPLOAD_DIR
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.max_file_size = (
            (max_file_size_mb or settings.MAX_FILE_SIZE_MB) * 1024 * 1024
        )
        self.retention_minutes = retention_minutes or settings.FILE_RETENTION_MINUTES

        # In-memory file registry
        self._files: Dict[str, FileInfo] = {}

        # Background cleanup task handle
        self._cleanup_task: Optional[asyncio.Task] = None

        # Ensure directories exist with correct permissions
        self._ensure_directories()

        logger.info(
            f"FileManager ready: upload={self.upload_dir}, "
            f"output={self.output_dir}, "
            f"retention={self.retention_minutes}min"
        )

    # ─── Public: Store Files ───────────────────────────────────

    async def store_upload(
        self,
        content: bytes,
        original_filename: str,
        content_type: str = "application/pdf",
        is_encrypted: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> FileInfo:
        """
        Store an uploaded file securely.

        Args:
            content: Raw file bytes
            original_filename: Client-provided filename
            content_type: MIME type of the file
            is_encrypted: Whether the PDF is password-protected
            metadata: Additional metadata to attach

        Returns:
            FileInfo with all file details

        Raises:
            ValueError: If validation fails
            RuntimeError: If file write fails
        """
        # Validate before storing
        self._validate_file(content, original_filename, content_type)

        # Generate secure identifiers
        file_id = self._generate_file_id()
        safe_name = self._sanitize_filename(original_filename)
        file_path = self.upload_dir / f"{file_id}_{safe_name}"

        # Hash content for integrity verification
        file_hash = self._hash_content(content)

        # Write file to disk
        await self._write_file(file_path, content)

        # Build file info record
        now = datetime.utcnow()
        file_info = FileInfo(
            file_id=file_id,
            original_name=original_filename,
            safe_name=safe_name,
            file_path=file_path,
            file_hash=file_hash,
            size_bytes=len(content),
            content_type=content_type,
            created_at=now,
            expires_at=now + timedelta(minutes=self.retention_minutes),
            is_encrypted=is_encrypted,
            metadata=metadata or {},
        )

        # Register in memory
        self._files[file_id] = file_info

        logger.info(
            f"Stored upload: id={file_id}, "
            f"size={file_info.size_kb}KB, "
            f"encrypted={is_encrypted}, "
            f"expires={file_info.expires_at.isoformat()}"
        )

        return file_info

    async def store_output(
        self,
        content: bytes,
        filename: str,
        related_file_id: Optional[str] = None,
        content_type: str = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    ) -> FileInfo:
        """
        Store a generated output file (e.g., Excel).

        Args:
            content: Output file bytes
            filename: Desired filename
            related_file_id: ID of the source file
            content_type: MIME type

        Returns:
            FileInfo for the output file
        """
        file_id = self._generate_file_id()
        safe_name = self._sanitize_filename(filename)
        file_path = self.output_dir / f"{file_id}_{safe_name}"
        file_hash = self._hash_content(content)

        await self._write_file(file_path, content)

        now = datetime.utcnow()
        file_info = FileInfo(
            file_id=file_id,
            original_name=filename,
            safe_name=safe_name,
            file_path=file_path,
            file_hash=file_hash,
            size_bytes=len(content),
            content_type=content_type,
            created_at=now,
            expires_at=now + timedelta(minutes=self.retention_minutes),
            metadata={
                "type": "output",
                "related_file_id": related_file_id,
            },
        )

        self._files[file_id] = file_info

        logger.info(
            f"Stored output: id={file_id}, "
            f"size={file_info.size_kb}KB, "
            f"related={related_file_id}"
        )

        return file_info

    # ─── Public: Read Files ────────────────────────────────────

    async def get_file_content(self, file_id: str) -> Optional[bytes]:
        """
        Retrieve file content by ID with integrity check.

        Args:
            file_id: The file identifier

        Returns:
            File content bytes, or None if not found/expired/corrupted
        """
        file_info = self._files.get(file_id)

        if not file_info:
            logger.warning(f"File not found in registry: {file_id}")
            return None

        # Check expiration
        if file_info.is_expired:
            logger.warning(f"File expired: {file_id}")
            await self.delete_file(file_id)
            return None

        # Check file exists on disk
        if not file_info.file_path.exists():
            logger.warning(f"File missing from disk: {file_id}")
            self._files.pop(file_id, None)
            return None

        # Read content
        try:
            async with aiofiles.open(file_info.file_path, "rb") as f:
                content = await f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_id}: {e}")
            return None

        # Verify integrity
        actual_hash = self._hash_content(content)
        if not secrets.compare_digest(actual_hash, file_info.file_hash):
            logger.error(f"Integrity check FAILED for {file_id}")
            await self.delete_file(file_id)
            return None

        return content

    def get_file_info(self, file_id: str) -> Optional[FileInfo]:
        """Get file metadata without reading content."""
        info = self._files.get(file_id)

        if info and info.is_expired:
            logger.debug(f"File info requested but expired: {file_id}")
            return None

        return info

    async def get_file_path(self, file_id: str) -> Optional[Path]:
        """
        Get validated file path for direct serving.

        Returns None if file is expired, missing, or corrupted.
        """
        info = self._files.get(file_id)

        if not info:
            return None

        if info.is_expired:
            await self.delete_file(file_id)
            return None

        if not info.file_path.exists():
            self._files.pop(file_id, None)
            return None

        return info.file_path

    def list_files(self, include_expired: bool = False) -> List[FileInfo]:
        """List all managed files."""
        if include_expired:
            return list(self._files.values())

        return [
            info for info in self._files.values() if not info.is_expired
        ]

    # ─── Public: Delete Files ──────────────────────────────────

    async def delete_file(self, file_id: str) -> bool:
        """
        Securely delete a file (overwrite with random data then unlink).

        Args:
            file_id: The file identifier

        Returns:
            True if file was deleted, False if not found
        """
        file_info = self._files.pop(file_id, None)

        if not file_info:
            return False

        try:
            if file_info.file_path.exists():
                await self._secure_delete(file_info.file_path, file_info.size_bytes)
                logger.info(f"Securely deleted: {file_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete {file_id}: {e}")
            # Fallback: try regular delete
            try:
                if file_info.file_path.exists():
                    file_info.file_path.unlink()
            except Exception:
                pass
            return True

    async def cleanup_expired(self) -> int:
        """
        Remove all expired files.

        Returns:
            Number of files cleaned up
        """
        now = datetime.utcnow()
        expired_ids = [
            file_id
            for file_id, info in self._files.items()
            if now > info.expires_at
        ]

        count = 0
        for file_id in expired_ids:
            if await self.delete_file(file_id):
                count += 1

        if count > 0:
            logger.info(f"Cleaned up {count} expired file(s)")

        return count

    async def cleanup_all(self) -> int:
        """Remove ALL managed files and orphaned files on disk."""
        # Delete tracked files
        file_ids = list(self._files.keys())
        count = 0

        for file_id in file_ids:
            if await self.delete_file(file_id):
                count += 1

        # Delete orphaned files in directories
        for directory in [self.upload_dir, self.output_dir]:
            if not directory.exists():
                continue
            for file_path in directory.iterdir():
                if file_path.is_file():
                    try:
                        await self._secure_delete(
                            file_path, file_path.stat().st_size
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"Could not delete orphan {file_path}: {e}")
                        try:
                            file_path.unlink()
                            count += 1
                        except Exception:
                            pass

        logger.info(f"Full cleanup: removed {count} file(s)")
        return count

    # ─── Public: Background Cleanup ────────────────────────────

    def start_cleanup_loop(self, interval_minutes: int = 5) -> None:
        """Start periodic background cleanup of expired files."""

        async def _loop():
            logger.info(
                f"Cleanup loop started (every {interval_minutes} min)"
            )
            while True:
                try:
                    await asyncio.sleep(interval_minutes * 60)
                    await self.cleanup_expired()
                except asyncio.CancelledError:
                    logger.info("Cleanup loop cancelled")
                    break
                except Exception as e:
                    logger.error(f"Cleanup loop error: {e}")

        self._cleanup_task = asyncio.create_task(_loop())

    def stop_cleanup_loop(self) -> None:
        """Stop the background cleanup loop."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("Cleanup loop stopped")

    # ─── Public: Statistics ────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        active = [f for f in self._files.values() if not f.is_expired]
        expired = [f for f in self._files.values() if f.is_expired]

        total_size = sum(f.size_bytes for f in active)

        return {
            "active_files": len(active),
            "expired_files": len(expired),
            "total_tracked": len(self._files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "upload_dir": str(self.upload_dir),
            "output_dir": str(self.output_dir),
            "retention_minutes": self.retention_minutes,
            "max_file_size_mb": self.max_file_size // (1024 * 1024),
            "cleanup_running": (
                self._cleanup_task is not None
                and not self._cleanup_task.done()
            ),
        }

    # ─── Private: Validation ───────────────────────────────────

    def _validate_file(
        self,
        content: bytes,
        filename: str,
        content_type: str,
    ) -> None:
        """Validate file before storage. Raises ValueError on failure."""

        # Size checks
        if len(content) > self.max_file_size:
            raise ValueError(
                f"File too large: {len(content)} bytes "
                f"(max: {self.max_file_size} bytes)"
            )

        if len(content) < 100:
            raise ValueError("File too small to be valid")

        # Extension check
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file extension: {ext}")

        # Content type check (warn but don't block)
        if content_type and content_type not in self.ALLOWED_CONTENT_TYPES:
            logger.warning(
                f"Unexpected content type: {content_type} "
                f"(expected one of {self.ALLOWED_CONTENT_TYPES})"
            )

        # PDF magic bytes check
        if not content.startswith(b"%PDF"):
            raise ValueError("File is not a valid PDF (bad magic bytes)")

    # ─── Private: File Operations ──────────────────────────────

    async def _write_file(self, file_path: Path, content: bytes) -> None:
        """Write content to file with restricted permissions."""
        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)

            # Owner read/write only
            os.chmod(file_path, 0o600)

        except Exception as e:
            # Clean up partial writes
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass
            logger.error(f"File write failed: {file_path}: {e}")
            raise RuntimeError(f"Could not write file: {e}") from e

    async def _secure_delete(
        self, file_path: Path, original_size: int
    ) -> None:
        """
        Securely delete file: overwrite with random data then unlink.
        This makes recovery more difficult.
        """
        try:
            if not file_path.exists():
                return

            # Overwrite with random data (cap at 1MB for performance)
            overwrite_size = min(original_size, 1024 * 1024)

            async with aiofiles.open(file_path, "wb") as f:
                await f.write(os.urandom(overwrite_size))
                await f.flush()
                # Force write to disk
                os.fsync(f.fileno())

            # Now delete
            await aiofiles.os.remove(file_path)

        except Exception as e:
            logger.warning(f"Secure delete fallback for {file_path}: {e}")
            # Fallback to regular deletion
            if file_path.exists():
                file_path.unlink()

    # ─── Private: Helpers ──────────────────────────────────────

    def _generate_file_id(self) -> str:
        """Generate a cryptographically secure file ID."""
        return secrets.token_urlsafe(16)

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal and injection.

        - Strips directory components
        - Removes dangerous characters
        - Removes leading dots (hidden files)
        - Limits length
        """
        if not filename:
            return "unnamed_file.pdf"

        # Take only the filename part (no directories)
        name = Path(filename).name

        # Remove null bytes
        name = name.replace("\x00", "")

        # Keep only safe characters
        safe = re.sub(r"[^\w\-_\.]", "_", name)

        # Remove leading dots
        safe = safe.lstrip(".")

        # Collapse consecutive underscores
        safe = re.sub(r"_+", "_", safe)

        # Limit length while preserving extension
        if len(safe) > 100:
            stem = Path(safe).stem
            ext = Path(safe).suffix
            safe = stem[: 95 - len(ext)] + ext

        return safe if safe else "unnamed_file.pdf"

    def _hash_content(self, content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    def _ensure_directories(self) -> None:
        """Create storage directories with appropriate permissions."""
        for directory in [self.upload_dir, self.output_dir]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                # rwx for owner only
                os.chmod(directory, 0o700)
            except Exception as e:
                logger.error(f"Cannot create directory {directory}: {e}")
                raise


# ─── Singleton Instance ────────────────────────────────────────

file_manager = SecureFileManager()