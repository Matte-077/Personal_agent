"""
Advisor module: intelligent consultative engine and proactive retrieval service.
"""

from src.advisor.assistant import AdvisorService
from src.advisor.car_tco import calculate_import_tco, is_phev_model

__all__ = ["AdvisorService", "calculate_import_tco", "is_phev_model"]
