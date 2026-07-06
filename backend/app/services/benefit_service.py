"""Benefit service — re-exported from app.core.benefits for backward compatibility."""

from app.core.benefits import BenefitAuthHandler, BenefitService, benefit_service

__all__ = ["BenefitAuthHandler", "BenefitService", "benefit_service"]
