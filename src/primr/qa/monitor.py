"""
QA monitoring and metrics collection for enhanced quality assurance system.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

from primr.config.models import PrimrModels

logger = logging.getLogger(__name__)


@dataclass
class QAMetrics:
    """QA performance metrics for monitoring."""
    total_assessments: int = 0
    successful_assessments: int = 0
    failed_assessments: int = 0
    parsing_failures: int = 0
    rate_limit_errors: int = 0
    quota_errors: int = 0
    network_errors: int = 0
    average_grade: float = 0.0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0
    ready_for_use_count: int = 0
    needs_work_count: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_assessments == 0:
            return 0.0
        return (self.successful_assessments / self.total_assessments) * 100
    
    @property
    def parsing_success_rate(self) -> float:
        """Calculate parsing success rate percentage."""
        if self.successful_assessments == 0:
            return 0.0
        return ((self.successful_assessments - self.parsing_failures) / self.successful_assessments) * 100


@dataclass
class QAAssessmentLog:
    """Individual QA assessment log entry."""
    timestamp: str
    company_name: str
    report_type: str
    grade: int
    confidence_level: str
    ready_for_use: bool
    parsing_success: bool
    error_type: Optional[str] = None
    processing_time_ms: Optional[int] = None
    model_used: str = PrimrModels.QA_MODEL
    fallback_used: bool = False
    retry_count: int = 0


class QAMonitor:
    """Monitor QA system performance and collect metrics."""
    
    def __init__(self, log_dir: Path = None):
        """Initialize QA monitor with logging directory."""
        self.log_dir = log_dir or Path("logs/qa")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.metrics_file = self.log_dir / "qa_metrics.json"
        self.assessments_log = self.log_dir / "qa_assessments.jsonl"
        
        # In-memory metrics for current session
        self.session_metrics = QAMetrics()
        self.session_logs: List[QAAssessmentLog] = []
        
        logger.info(f"QA monitoring initialized with log directory: {self.log_dir}")
    
    def log_assessment(self, 
                      company_name: str,
                      report_type: str,
                      grade: int,
                      confidence_level: str,
                      ready_for_use: bool,
                      parsing_success: bool,
                      error_type: Optional[str] = None,
                      processing_time_ms: Optional[int] = None,
                      model_used: str = PrimrModels.QA_MODEL,
                      fallback_used: bool = False,
                      retry_count: int = 0) -> None:
        """
        Log a QA assessment result.
        
        Args:
            company_name: Name of company assessed
            report_type: Type of report (AI Strategy, Comprehensive, etc.)
            grade: Numerical grade (0-100)
            confidence_level: Confidence level (high, medium, low)
            ready_for_use: Whether report is ready for use
            parsing_success: Whether JSON parsing succeeded
            error_type: Type of error if any occurred
            processing_time_ms: Processing time in milliseconds
            model_used: AI model used for assessment
            fallback_used: Whether fallback model was used
            retry_count: Number of retries attempted
        """
        try:
            # Create log entry
            log_entry = QAAssessmentLog(
                timestamp=datetime.now().isoformat(),
                company_name=company_name,
                report_type=report_type,
                grade=grade,
                confidence_level=confidence_level,
                ready_for_use=ready_for_use,
                parsing_success=parsing_success,
                error_type=error_type,
                processing_time_ms=processing_time_ms,
                model_used=model_used,
                fallback_used=fallback_used,
                retry_count=retry_count
            )
            
            # Add to session logs
            self.session_logs.append(log_entry)
            
            # Update session metrics
            self._update_session_metrics(log_entry)
            
            # Append to persistent log file
            self._append_to_log_file(log_entry)
            
            # Update persistent metrics
            self._update_persistent_metrics()
            
            logger.debug(f"Logged QA assessment for {company_name}: grade={grade}, confidence={confidence_level}")
            
        except Exception as e:
            logger.error(f"Failed to log QA assessment for {company_name}: {e}")
    
    def _update_session_metrics(self, log_entry: QAAssessmentLog) -> None:
        """Update in-memory session metrics."""
        metrics = self.session_metrics
        
        metrics.total_assessments += 1
        
        if log_entry.error_type:
            metrics.failed_assessments += 1
            
            # Categorize error types
            error_lower = log_entry.error_type.lower()
            if "rate limit" in error_lower or "429" in error_lower:
                metrics.rate_limit_errors += 1
            elif "quota" in error_lower:
                metrics.quota_errors += 1
            elif "network" in error_lower or "timeout" in error_lower:
                metrics.network_errors += 1
        else:
            metrics.successful_assessments += 1
            
            # Update grade average
            total_successful = metrics.successful_assessments
            current_avg = metrics.average_grade
            metrics.average_grade = ((current_avg * (total_successful - 1)) + log_entry.grade) / total_successful
            
            # Update confidence counts
            if log_entry.confidence_level == "high":
                metrics.high_confidence_count += 1
            elif log_entry.confidence_level == "medium":
                metrics.medium_confidence_count += 1
            else:
                metrics.low_confidence_count += 1
            
            # Update readiness counts
            if log_entry.ready_for_use:
                metrics.ready_for_use_count += 1
            else:
                metrics.needs_work_count += 1
            
            # Update parsing failures
            if not log_entry.parsing_success:
                metrics.parsing_failures += 1
    
    def _append_to_log_file(self, log_entry: QAAssessmentLog) -> None:
        """Append log entry to persistent JSONL file."""
        try:
            with open(self.assessments_log, 'a', encoding='utf-8') as f:
                json.dump(asdict(log_entry), f)
                f.write('\n')
        except Exception as e:
            logger.error(f"Failed to append to log file: {e}")
    
    def _update_persistent_metrics(self) -> None:
        """Update persistent metrics file."""
        try:
            # Load existing metrics if they exist
            persistent_metrics = QAMetrics()
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(persistent_metrics, key):
                            setattr(persistent_metrics, key, value)
            
            # Add session metrics to persistent metrics
            persistent_metrics.total_assessments += 1
            if self.session_logs:
                latest_log = self.session_logs[-1]
                if latest_log.error_type:
                    persistent_metrics.failed_assessments += 1
                else:
                    persistent_metrics.successful_assessments += 1
                    
                    # Update running average
                    total = persistent_metrics.successful_assessments
                    if total > 0:
                        current_avg = persistent_metrics.average_grade
                        persistent_metrics.average_grade = ((current_avg * (total - 1)) + latest_log.grade) / total
            
            # Save updated metrics
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(persistent_metrics), f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to update persistent metrics: {e}")
    
    def get_session_metrics(self) -> QAMetrics:
        """Get current session metrics."""
        return self.session_metrics
    
    def get_persistent_metrics(self) -> QAMetrics:
        """Load and return persistent metrics."""
        try:
            if not self.metrics_file.exists():
                return QAMetrics()
            
            with open(self.metrics_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                metrics = QAMetrics()
                for key, value in data.items():
                    if hasattr(metrics, key):
                        setattr(metrics, key, value)
                return metrics
        except Exception as e:
            logger.error(f"Failed to load persistent metrics: {e}")
            return QAMetrics()
    
    def get_recent_assessments(self, hours: int = 24) -> List[QAAssessmentLog]:
        """Get assessments from the last N hours."""
        try:
            if not self.assessments_log.exists():
                return []
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_logs = []
            
            with open(self.assessments_log, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        log_time = datetime.fromisoformat(data['timestamp'])
                        if log_time >= cutoff_time:
                            recent_logs.append(QAAssessmentLog(**data))
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
            
            return recent_logs
        except Exception as e:
            logger.error(f"Failed to get recent assessments: {e}")
            return []
    
    def generate_status_report(self) -> Dict[str, Any]:
        """Generate comprehensive status report."""
        try:
            session_metrics = self.get_session_metrics()
            persistent_metrics = self.get_persistent_metrics()
            recent_assessments = self.get_recent_assessments(24)
            
            # Calculate recent performance
            recent_success_rate = 0.0
            recent_avg_grade = 0.0
            if recent_assessments:
                successful_recent = [log for log in recent_assessments if not log.error_type]
                recent_success_rate = (len(successful_recent) / len(recent_assessments)) * 100
                if successful_recent:
                    recent_avg_grade = sum(log.grade for log in successful_recent) / len(successful_recent)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "session_metrics": asdict(session_metrics),
                "persistent_metrics": asdict(persistent_metrics),
                "recent_24h": {
                    "total_assessments": len(recent_assessments),
                    "success_rate": recent_success_rate,
                    "average_grade": recent_avg_grade
                },
                "system_health": {
                    "overall_success_rate": persistent_metrics.success_rate,
                    "parsing_success_rate": persistent_metrics.parsing_success_rate,
                    "meets_95_percent_target": persistent_metrics.success_rate >= 95.0,
                    "average_quality": persistent_metrics.average_grade
                }
            }
        except Exception as e:
            logger.error(f"Failed to generate status report: {e}")
            return {"error": str(e)}
    
    def print_status_summary(self) -> None:
        """Print a concise status summary to console."""
        try:
            report = self.generate_status_report()
            
            print("\nQA System Status Summary")
            print("=" * 40)
            
            session = report.get("session_metrics", {})
            persistent = report.get("persistent_metrics", {})
            health = report.get("system_health", {})
            
            print(f"Session: {session.get('total_assessments', 0)} assessments")
            print(f"Success Rate: {session.get('success_rate', 0):.1f}%")
            
            if persistent.get('total_assessments', 0) > 0:
                print(f"Overall: {persistent.get('total_assessments', 0)} total assessments")
                print(f"Overall Success: {health.get('overall_success_rate', 0):.1f}%")
                print(f"Average Grade: {health.get('average_quality', 0):.1f}/100")
                
                target_met = health.get('meets_95_percent_target', False)
                print(f"95% Target: {'✓ Met' if target_met else '✗ Not Met'}")
            
        except Exception as e:
            logger.error(f"Failed to print status summary: {e}")