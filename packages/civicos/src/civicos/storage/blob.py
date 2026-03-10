"""
BlobStorage protocol for large file persistence.

Defines the interface for storing binary objects (PDFs, audio, transcripts).
Part of the 4-stage pipeline: discover -> ingest -> store -> index.

Unlike StorageBackend (structured data in SQLite/Postgres), BlobStorage
handles raw binary files that are too large for database storage.

Use cases:
- Agenda packet PDFs
- Meeting audio/video files
- Raw transcripts before processing
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class BlobStats:
    """
    Statistics for a blob storage backend.

    Used by dashboards to show storage utilization.
    """

    total_objects: int
    total_bytes: int

    # By content type (e.g., {"application/pdf": 50, "audio/mpeg": 10})
    by_content_type: Dict[str, int] = field(default_factory=dict)

    # Extra backend-specific stats
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_objects": self.total_objects,
            "total_bytes": self.total_bytes,
            "by_content_type": self.by_content_type,
            "metadata": self.metadata,
        }


@dataclass
class BlobValidationResult:
    """
    Result of blob storage validation.

    Preflight check for storage connectivity and permissions.
    """

    is_valid: bool  # All checks passed
    connected: bool  # Can connect to storage
    writable: bool  # Can write to storage

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    check_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "connected": self.connected,
            "writable": self.writable,
            "errors": self.errors,
            "warnings": self.warnings,
            "check_duration_ms": self.check_duration_ms,
        }


@runtime_checkable
class BlobStorage(Protocol):
    """
    Protocol for binary object storage (R2, S3, local filesystem).

    Handles storage of large files that don't belong in the database:
    - PDFs (agenda packets, staff reports)
    - Audio/video files
    - Raw transcripts

    Implementations:
    - LocalBlobBackend: Filesystem storage for development
    - R2Backend: Cloudflare R2 for production (S3-compatible)

    Usage:
        blob = get_blob_storage()

        # Validate before use
        result = blob.validate()
        if not result.is_valid:
            raise RuntimeError(result.errors)

        # Upload a PDF
        url = blob.upload(
            key="san-rafael/2024-01-15/agenda.pdf",
            data=pdf_bytes,
            content_type="application/pdf"
        )

        # Download later
        data = blob.download("san-rafael/2024-01-15/agenda.pdf")
    """

    @property
    def backend_type(self) -> str:
        """Type identifier: 'local', 'r2', 's3'."""
        ...

    def validate(self) -> BlobValidationResult:
        """
        Validate blob storage connectivity and permissions.

        Preflight check that fails fast with clear error messages for:
        - Storage connectivity issues
        - Missing buckets or directories
        - Permission problems

        Returns:
            BlobValidationResult with is_valid, errors, warnings
        """
        ...

    def upload(
        self,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload binary data to storage.

        Args:
            key: Storage key/path (e.g., "san-rafael/2024-01-15/agenda.pdf")
            data: Binary data to store
            content_type: MIME type (e.g., "application/pdf")
            metadata: Optional key-value metadata

        Returns:
            URL or path to the stored object

        Raises:
            StorageError: If upload fails
        """
        ...

    def download(self, key: str) -> bytes:
        """
        Download binary data from storage.

        Args:
            key: Storage key/path

        Returns:
            Binary data

        Raises:
            KeyError: If object not found
            StorageError: If download fails
        """
        ...

    def exists(self, key: str) -> bool:
        """
        Check if an object exists in storage.

        Args:
            key: Storage key/path

        Returns:
            True if object exists, False otherwise
        """
        ...

    def delete(self, key: str) -> bool:
        """
        Delete an object from storage.

        Args:
            key: Storage key/path

        Returns:
            True if deleted, False if not found
        """
        ...

    def list_keys(self, prefix: str = "") -> List[str]:
        """
        List object keys matching a prefix.

        Args:
            prefix: Key prefix to filter (e.g., "san-rafael/2024-01-")

        Returns:
            List of matching keys
        """
        ...

    def get_stats(self) -> BlobStats:
        """
        Get storage statistics.

        Used by dashboards and monitoring.

        Returns:
            BlobStats with counts and size info
        """
        ...


class LocalBlobBackend:
    """
    Filesystem-based blob storage for local development.

    Stores files in a local directory hierarchy.

    Usage:
        blob = LocalBlobBackend("data/blobs")
        blob.upload("test/file.pdf", pdf_data, "application/pdf")
        data = blob.download("test/file.pdf")
    """

    def __init__(self, base_path: str = "data/blobs"):
        """
        Initialize local blob storage.

        Args:
            base_path: Root directory for blob storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._metadata: Dict[str, Dict[str, str]] = {}

    @property
    def backend_type(self) -> str:
        """Type identifier."""
        return "local"

    def validate(self) -> BlobValidationResult:
        """Validate local storage is accessible and writable."""
        import time

        start = time.perf_counter()
        errors: List[str] = []
        warnings: List[str] = []

        # Check directory exists
        connected = self.base_path.exists()
        if not connected:
            errors.append(f"Base path does not exist: {self.base_path}")

        # Check writable
        writable = False
        if connected:
            test_file = self.base_path / ".write_test"
            try:
                test_file.write_bytes(b"test")
                test_file.unlink()
                writable = True
            except Exception as e:
                errors.append(f"Directory not writable: {e}")

        is_valid = connected and writable
        duration_ms = (time.perf_counter() - start) * 1000

        return BlobValidationResult(
            is_valid=is_valid,
            connected=connected,
            writable=writable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=duration_ms,
        )

    def upload(
        self,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload data to local filesystem."""
        file_path = self.base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)

        # Store metadata in memory (could use sidecar files)
        if content_type or metadata:
            self._metadata[key] = {
                **({"content_type": content_type} if content_type else {}),
                **(metadata or {}),
            }

        return str(file_path)

    def download(self, key: str) -> bytes:
        """Download data from local filesystem."""
        file_path = self.base_path / key
        if not file_path.exists():
            raise KeyError(f"Object not found: {key}")
        return file_path.read_bytes()

    def exists(self, key: str) -> bool:
        """Check if file exists."""
        return (self.base_path / key).exists()

    def delete(self, key: str) -> bool:
        """Delete file from filesystem."""
        file_path = self.base_path / key
        if file_path.exists():
            file_path.unlink()
            self._metadata.pop(key, None)
            return True
        return False

    def list_keys(self, prefix: str = "") -> List[str]:
        """List files matching prefix."""
        search_path = self.base_path / prefix if prefix else self.base_path
        if not search_path.exists():
            # If prefix is a partial path, search parent
            search_path = self.base_path

        keys = []
        for path in search_path.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(self.base_path)
                key = str(rel_path)
                if key.startswith(prefix):
                    keys.append(key)
        return sorted(keys)

    def get_stats(self) -> BlobStats:
        """Get storage statistics."""
        total_objects = 0
        total_bytes = 0
        by_content_type: Dict[str, int] = {}

        for path in self.base_path.rglob("*"):
            if path.is_file():
                total_objects += 1
                total_bytes += path.stat().st_size

                # Try to determine content type from metadata or extension
                key = str(path.relative_to(self.base_path))
                ct = self._metadata.get(key, {}).get("content_type")
                if ct:
                    by_content_type[ct] = by_content_type.get(ct, 0) + 1

        return BlobStats(
            total_objects=total_objects,
            total_bytes=total_bytes,
            by_content_type=by_content_type,
            metadata={"base_path": str(self.base_path)},
        )


class R2Backend:
    """
    Cloudflare R2 blob storage backend (S3-compatible).

    Uses boto3 with R2's S3-compatible API for production storage.
    10GB free tier with zero egress fees.

    Environment variables:
    - BLOB_STORAGE_URL: r2://account_id/bucket_name
    - R2_ACCESS_KEY_ID: R2 API token access key
    - R2_SECRET_ACCESS_KEY: R2 API token secret

    Usage:
        blob = R2Backend.from_env()
        blob.upload("test/file.pdf", pdf_data, "application/pdf")
        data = blob.download("test/file.pdf")
    """

    def __init__(
        self,
        account_id: str,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
    ):
        """
        Initialize R2 backend.

        Args:
            account_id: Cloudflare account ID
            bucket_name: R2 bucket name
            access_key_id: R2 API token access key ID
            secret_access_key: R2 API token secret access key
        """
        import boto3

        self.account_id = account_id
        self.bucket_name = bucket_name

        # Create S3 client pointing to R2 endpoint
        self.s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",  # R2 uses 'auto' for region
        )

    @classmethod
    def from_env(cls) -> "R2Backend":
        """
        Create R2Backend from environment variables.

        Required environment variables:
        - BLOB_STORAGE_URL: r2://account_id/bucket_name
        - R2_ACCESS_KEY_ID: R2 API token access key
        - R2_SECRET_ACCESS_KEY: R2 API token secret

        Returns:
            R2Backend instance

        Raises:
            ValueError: If required environment variables are missing
        """
        url = os.getenv("BLOB_STORAGE_URL")
        if not url:
            raise ValueError("BLOB_STORAGE_URL environment variable not set")

        if not url.startswith("r2://"):
            raise ValueError(f"Invalid R2 URL format: {url}")

        # Parse r2://account_id/bucket_name
        parts = url.replace("r2://", "").split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid R2 URL format: {url}")

        account_id, bucket_name = parts

        access_key = os.getenv("R2_ACCESS_KEY_ID")
        secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

        if not access_key or not secret_key:
            raise ValueError("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY must be set")

        return cls(account_id, bucket_name, access_key, secret_key)

    @classmethod
    def from_url(cls, url: str) -> "R2Backend":
        """
        Create R2Backend from URL and environment credentials.

        Args:
            url: R2 URL in format r2://account_id/bucket_name

        Returns:
            R2Backend instance
        """
        if not url.startswith("r2://"):
            raise ValueError(f"Invalid R2 URL format: {url}")

        parts = url.replace("r2://", "").split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid R2 URL format: {url}")

        account_id, bucket_name = parts

        access_key = os.getenv("R2_ACCESS_KEY_ID")
        secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

        if not access_key or not secret_key:
            raise ValueError("R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY must be set")

        return cls(account_id, bucket_name, access_key, secret_key)

    @property
    def backend_type(self) -> str:
        """Type identifier."""
        return "r2"

    def validate(self) -> BlobValidationResult:
        """Validate R2 connectivity and permissions."""
        import time

        from botocore.exceptions import ClientError

        start = time.perf_counter()
        errors: List[str] = []
        warnings: List[str] = []
        connected = False
        writable = False

        try:
            # Check bucket exists and is accessible
            self.s3.head_bucket(Bucket=self.bucket_name)
            connected = True

            # Check write permission with a test object
            test_key = ".civic_write_test"
            try:
                self.s3.put_object(
                    Bucket=self.bucket_name,
                    Key=test_key,
                    Body=b"test",
                )
                self.s3.delete_object(Bucket=self.bucket_name, Key=test_key)
                writable = True
            except ClientError as e:
                errors.append(f"Bucket not writable: {e}")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                errors.append(f"Bucket not found: {self.bucket_name}")
            elif error_code == "403":
                errors.append(f"Access denied to bucket: {self.bucket_name}")
            else:
                errors.append(f"R2 connection error: {e}")
        except Exception as e:
            errors.append(f"R2 connection error: {e}")

        is_valid = connected and writable
        duration_ms = (time.perf_counter() - start) * 1000

        return BlobValidationResult(
            is_valid=is_valid,
            connected=connected,
            writable=writable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=duration_ms,
        )

    def upload(
        self,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload data to R2."""
        extra_args: Dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata

        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            **extra_args,
        )

        # Log cost (Class A write operation)
        self._log_cost('upload', len(data), key, content_type)

        # Return the R2 URL (not public unless configured)
        return f"r2://{self.account_id}/{self.bucket_name}/{key}"

    def download(self, key: str) -> bytes:
        """Download data from R2."""
        from botocore.exceptions import ClientError

        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=key)
            data = response["Body"].read()
            # Log cost (Class B read operation)
            self._log_cost('download', len(data), key)
            return data
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                raise KeyError(f"Object not found: {key}")
            raise

    def _log_cost(
        self, operation: str, bytes_transferred: int, key: str, content_type: Optional[str] = None
    ) -> None:
        """Log R2 operation cost. Never raises."""
        try:
            from civicos_services.core.cost_tracking import log_r2_cost

            meta: Dict[str, Any] = {'key': key}
            if content_type:
                meta['content_type'] = content_type
            log_r2_cost(
                operation=operation,
                bytes_transferred=bytes_transferred,
                metadata=meta,
            )
        except ImportError:
            pass
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        """Check if object exists in R2."""
        from botocore.exceptions import ClientError

        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                return False
            raise

    def delete(self, key: str) -> bool:
        """Delete object from R2."""
        from botocore.exceptions import ClientError

        try:
            # Check if exists first (delete always succeeds even for non-existent)
            self.s3.head_object(Bucket=self.bucket_name, Key=key)
            self.s3.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                return False
            raise

    def list_keys(self, prefix: str = "") -> List[str]:
        """List objects matching prefix."""
        keys = []
        paginator = self.s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])

        return sorted(keys)

    def get_stats(self) -> BlobStats:
        """Get storage statistics."""
        total_objects = 0
        total_bytes = 0
        by_content_type: Dict[str, int] = {}

        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name):
            for obj in page.get("Contents", []):
                total_objects += 1
                total_bytes += obj.get("Size", 0)
                # Note: Content type requires head_object for each file
                # which is expensive, so we skip it in stats

        return BlobStats(
            total_objects=total_objects,
            total_bytes=total_bytes,
            by_content_type=by_content_type,
            metadata={
                "bucket": self.bucket_name,
                "account_id": self.account_id,
            },
        )


def get_blob_storage(url: Optional[str] = None) -> BlobStorage:
    """
    Factory function to get the appropriate blob storage backend.

    Selects backend based on BLOB_STORAGE_URL format:
    - r2://account_id/bucket -> R2Backend
    - (default)              -> LocalBlobBackend

    Args:
        url: Blob storage URL. If not provided, uses BLOB_STORAGE_URL
             environment variable. If neither is set, defaults to local.

    Returns:
        BlobStorage instance (LocalBlobBackend or R2Backend)

    Examples:
        # Use environment variable
        blob = get_blob_storage()

        # Explicit local
        blob = get_blob_storage("local://data/blobs")

        # Explicit R2
        blob = get_blob_storage("r2://account_id/bucket_name")
    """
    url = url or os.getenv("BLOB_STORAGE_URL")

    if url is None:
        # Default to local storage
        return LocalBlobBackend("data/blobs")

    if url.startswith("r2://"):
        return R2Backend.from_url(url)

    if url.startswith("local://"):
        path = url.replace("local://", "")
        return LocalBlobBackend(path)

    # Fallback: treat as local path
    return LocalBlobBackend(url)
