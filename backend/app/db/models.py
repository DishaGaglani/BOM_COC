import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, Text, Enum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


def gen_uuid():
    return str(uuid.uuid4())


class BOMStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class ValidationStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class BOM(Base):
    __tablename__ = "bom"

    bom_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    project_id = Column(String, index=True, nullable=False)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)
    status = Column(Enum(BOMStatus), default=BOMStatus.ACTIVE)

    items = relationship("BOMItem", back_populates="bom", cascade="all, delete-orphan")
    cocs = relationship("COC", back_populates="bom")


class BOMItem(Base):
    __tablename__ = "bom_items"

    item_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    bom_id = Column(UUID(as_uuid=False), ForeignKey("bom.bom_id"), nullable=False)
    part_id = Column(String, index=True)
    description = Column(Text)
    manufacturer = Column(String)
    model = Column(String)
    quantity = Column(Float)
    po_number = Column(String, index=True)
    requirements = Column(JSON, default=dict)  # extra fields: YOM, warranty, import flag, etc.

    bom = relationship("BOM", back_populates="items")


class COC(Base):
    __tablename__ = "coc"

    coc_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    bom_id = Column(UUID(as_uuid=False), ForeignKey("bom.bom_id"), nullable=False)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    document_type = Column(String, default="unknown")  # coc / invoice / packing_list / test_certificate / other
    status = Column(String, default="pending")  # pending / extracted / validated

    bom = relationship("BOM", back_populates="cocs")
    entities = relationship("COCEntity", back_populates="coc", cascade="all, delete-orphan")
    validations = relationship("Validation", back_populates="coc", cascade="all, delete-orphan")
    annotations = relationship("Annotation", back_populates="coc", cascade="all, delete-orphan")


class COCEntity(Base):
    __tablename__ = "coc_entities"

    entity_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    coc_id = Column(UUID(as_uuid=False), ForeignKey("coc.coc_id"), nullable=False)
    field_name = Column(String, index=True)  # canonical field, e.g. part_id
    field_value = Column(Text)
    confidence = Column(Float, default=1.0)
    page = Column(Integer)
    bbox = Column(JSON)  # [x0, y0, x1, y1]
    extraction_method = Column(String)  # table / ocr / llm

    coc = relationship("COC", back_populates="entities")


class Validation(Base):
    __tablename__ = "validations"

    validation_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    coc_id = Column(UUID(as_uuid=False), ForeignKey("coc.coc_id"), nullable=False)
    item_id = Column(UUID(as_uuid=False), ForeignKey("bom_items.item_id"), nullable=True)
    parameter = Column(String, nullable=False)  # e.g. po_number, quantity
    expected_value = Column(Text)
    actual_value = Column(Text)
    status = Column(Enum(ValidationStatus), nullable=False)
    reason = Column(Text)

    coc = relationship("COC", back_populates="validations")


class Annotation(Base):
    __tablename__ = "annotations"

    annotation_id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    coc_id = Column(UUID(as_uuid=False), ForeignKey("coc.coc_id"), nullable=False)
    page = Column(Integer, nullable=False)
    bbox = Column(JSON, nullable=False)
    parameter = Column(String)
    status = Column(Enum(ValidationStatus))
    comment = Column(Text)

    coc = relationship("COC", back_populates="annotations")
