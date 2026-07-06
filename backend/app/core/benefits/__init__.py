"""Benefits module — member entitlements and feature gatekeeping."""

from app.core.benefits.models import BenefitErrorDetail, create_benefit_error_detail
from app.core.benefits.service import BenefitAuthHandler, BenefitService, benefit_service

__all__ = [
    "BenefitAuthHandler",
    "BenefitErrorDetail",
    "BenefitService",
    "benefit_service",
    "create_benefit_error_detail",
]
