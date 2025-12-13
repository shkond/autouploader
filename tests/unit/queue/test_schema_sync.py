"""Tests for schema and model field synchronization.

These tests ensure that QueueJobCreate, QueueJob schema, and QueueJobModel
have consistent fields to prevent runtime errors like 'invalid keyword argument'.
"""

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

from app.models import QueueJobModel
from app.queue.schemas import (
    QUEUE_JOB_CREATE_FIELDS,
    QUEUE_JOB_SHARED_FIELDS,
    QueueJob,
    QueueJobBase,
    QueueJobCreate,
)


def get_pydantic_fields(model: type[BaseModel]) -> set[str]:
    """Get all field names from a Pydantic model."""
    return set(model.model_fields.keys())


def get_sqlalchemy_columns(model: type[DeclarativeBase]) -> set[str]:
    """Get all column names from a SQLAlchemy model."""
    # Use __table__.columns for SQLAlchemy 2.0
    return {column.name for column in model.__table__.columns}


class TestQueueJobBaseInheritance:
    """Test that schemas properly inherit from QueueJobBase."""

    @staticmethod
    def test_queue_job_create_inherits_base_fields():
        """QueueJobCreate should have all QueueJobBase fields."""
        base_fields = get_pydantic_fields(QueueJobBase)
        create_fields = get_pydantic_fields(QueueJobCreate)

        missing = base_fields - create_fields
        assert not missing, f"QueueJobCreate missing base fields: {missing}"

    @staticmethod
    def test_queue_job_inherits_base_fields():
        """QueueJob should have all QueueJobBase fields."""
        base_fields = get_pydantic_fields(QueueJobBase)
        job_fields = get_pydantic_fields(QueueJob)

        missing = base_fields - job_fields
        assert not missing, f"QueueJob missing base fields: {missing}"


class TestSchemaModelSynchronization:
    """Test synchronization between Pydantic schemas and SQLAlchemy model."""

    @staticmethod
    def test_queue_job_create_fields_exist_in_model():
        """All QueueJobCreate fields (except metadata) should exist in QueueJobModel."""
        create_fields = get_pydantic_fields(QueueJobCreate)
        model_columns = get_sqlalchemy_columns(QueueJobModel)

        # metadata -> metadata_json is a special case
        expected_in_model = create_fields - {"metadata"}

        missing = expected_in_model - model_columns
        assert not missing, (
            f"QueueJobCreate has fields not in QueueJobModel: {missing}. "
            f"Add these columns to QueueJobModel in models.py"
        )

    @staticmethod
    def test_queue_job_fields_exist_in_model():
        """All QueueJob fields (except metadata) should exist in QueueJobModel."""
        job_fields = get_pydantic_fields(QueueJob)
        model_columns = get_sqlalchemy_columns(QueueJobModel)

        # metadata -> metadata_json is a special case
        expected_in_model = job_fields - {"metadata"}

        missing = expected_in_model - model_columns
        assert not missing, (
            f"QueueJob has fields not in QueueJobModel: {missing}. "
            f"Add these columns to QueueJobModel in models.py"
        )

    @staticmethod
    def test_shared_fields_constant_matches_queue_job():
        """QUEUE_JOB_SHARED_FIELDS should match actual QueueJob fields."""
        job_fields = get_pydantic_fields(QueueJob)
        # Exclude metadata as it's handled specially
        job_fields_no_metadata = job_fields - {"metadata"}

        missing_from_constant = job_fields_no_metadata - QUEUE_JOB_SHARED_FIELDS
        extra_in_constant = QUEUE_JOB_SHARED_FIELDS - job_fields_no_metadata

        assert not missing_from_constant, (
            f"QUEUE_JOB_SHARED_FIELDS missing: {missing_from_constant}. "
            f"Update the constant in schemas.py"
        )
        assert not extra_in_constant, (
            f"QUEUE_JOB_SHARED_FIELDS has extra fields: {extra_in_constant}. "
            f"Update the constant in schemas.py"
        )

    @staticmethod
    def test_create_fields_constant_matches_queue_job_create():
        """QUEUE_JOB_CREATE_FIELDS should match QueueJobCreate base fields."""
        create_fields = get_pydantic_fields(QueueJobCreate)
        # Exclude metadata as it's handled specially
        create_fields_no_metadata = create_fields - {"metadata"}

        missing_from_constant = create_fields_no_metadata - QUEUE_JOB_CREATE_FIELDS
        extra_in_constant = QUEUE_JOB_CREATE_FIELDS - create_fields_no_metadata

        assert not missing_from_constant, (
            f"QUEUE_JOB_CREATE_FIELDS missing: {missing_from_constant}. "
            f"Update the constant in schemas.py"
        )
        assert not extra_in_constant, (
            f"QUEUE_JOB_CREATE_FIELDS has extra fields: {extra_in_constant}. "
            f"Update the constant in schemas.py"
        )

    @staticmethod
    def test_model_has_metadata_json_column():
        """QueueJobModel should have metadata_json column for storing VideoMetadata."""
        model_columns = get_sqlalchemy_columns(QueueJobModel)
        assert "metadata_json" in model_columns, (
            "QueueJobModel missing 'metadata_json' column. "
            "This is required to store VideoMetadata as JSON."
        )


class TestModelRequiredColumns:
    """Test that QueueJobModel has all required columns."""

    @staticmethod
    def test_model_has_id_column():
        """QueueJobModel must have an id column."""
        model_columns = get_sqlalchemy_columns(QueueJobModel)
        assert "id" in model_columns

    @staticmethod
    def test_model_has_user_id_column():
        """QueueJobModel must have a user_id column."""
        model_columns = get_sqlalchemy_columns(QueueJobModel)
        assert "user_id" in model_columns

    @staticmethod
    def test_model_has_timestamp_columns():
        """QueueJobModel must have timestamp columns."""
        model_columns = get_sqlalchemy_columns(QueueJobModel)
        required_timestamps = {"created_at", "updated_at", "started_at", "completed_at"}

        missing = required_timestamps - model_columns
        assert not missing, f"QueueJobModel missing timestamp columns: {missing}"

    @staticmethod
    def test_model_has_file_size_column():
        """QueueJobModel must have file_size column for validation."""
        model_columns = get_sqlalchemy_columns(QueueJobModel)
        assert "file_size" in model_columns, (
            "QueueJobModel missing 'file_size' column. "
            "This is required for file size validation before upload."
        )
