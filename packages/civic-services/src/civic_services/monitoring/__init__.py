"""
Civic platform monitoring and alerting.

Modules:
- error_alerting: Error rate monitoring and alerts
- monitoring_dashboard: Production monitoring dashboard
- automated_civic_refresh: Automated data refresh
- multi_platform_monitor: Multi-platform meeting monitoring
- unified_data_source_manager: Data source management
"""

from .error_alerting import (
    ErrorAlertManager,
    ErrorMetricsCollector,
    ErrorMetrics,
    check_error_rates,
)

__all__ = [
    "ErrorAlertManager",
    "ErrorMetricsCollector",
    "ErrorMetrics",
    "check_error_rates",
]
