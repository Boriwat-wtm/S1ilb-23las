from fastapi import APIRouter, File, UploadFile
from sqlalchemy import select

from ..categorize import suggest_category
from ..config import settings
from ..deps import CurrentUser, DbSession
from ..models import Transaction
from ..ocr import extract_slip
from ..schemas import CategoryOut, CategorySuggestion, SlipUploadResult
from ..storage import (
    build_object_path,
    create_signed_url,
    process_image,
    upload_slip,
    validate_upload,
)

router = APIRouter(prefix="/slips", tags=["slips"])


@router.post("/upload", response_model=SlipUploadResult)
async def upload(
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> SlipUploadResult:
    """Store a slip and prefill whatever we can from it.

    Extraction failure is a 200, not an error. The response just comes back
    with empty fields and a message, and the form opens for manual entry.
    The only real failures here are a bad file or storage being down.
    """
    raw = await file.read()
    validate_upload(file.content_type, len(raw))
    jpeg = process_image(raw)

    object_path = build_object_path()
    await upload_slip(jpeg, object_path)
    signed = await create_signed_url(object_path)

    extraction = await extract_slip(jpeg)

    # If the QR gave us a reference we have seen before, this slip is already
    # in the book — tell the client before it builds a duplicate.
    duplicate_of_id = None
    if extraction.slip_ref:
        existing = db.execute(
            select(Transaction).where(Transaction.slip_ref == extraction.slip_ref)
        ).scalar_one_or_none()
        if existing is not None:
            duplicate_of_id = existing.id

    suggestion = None
    if extraction.description:
        category, keyword = suggest_category(db, extraction.description)
        suggestion = CategorySuggestion(
            category=CategoryOut.model_validate(category) if category else None,
            matched_keyword=keyword,
        )

    message = extraction.error
    if message is None and not extraction.ok:
        message = (
            "เก็บสลิปแล้ว แต่ยังไม่ได้เปิดระบบอ่านสลิป — กรอกจำนวนเงินกับวันที่เอง"
            if settings.ocr_provider == "none"
            else "อ่านข้อมูลจากสลิปไม่ได้ — กรอกเอง"
        )

    return SlipUploadResult(
        slip_path=object_path,
        signed_url=signed,
        extraction_ok=extraction.ok,
        provider=extraction.provider,
        source=extraction.source,
        confidence=extraction.confidence,
        amount=extraction.amount,
        occurred_at=extraction.occurred_at,
        description=extraction.description,
        slip_ref=extraction.slip_ref,
        duplicate_of_id=duplicate_of_id,
        raw_text=extraction.raw_text,
        message=message,
        suggestion=suggestion,
    )
