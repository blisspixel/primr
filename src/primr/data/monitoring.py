"""
Real-time company monitoring module.

Tracks company changes, news, and updates over time.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable


class ChangeType(Enum):
    """Types of company changes."""

    NEWS = "news"
    LEADERSHIP = "leadership"
    FINANCIAL = "financial"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"
    LEGAL = "legal"
    ACQUISITION = "acquisition"
    EXPANSION = "expansion"
    LAYOFF = "layoff"
    OTHER = "other"


class ChangeSeverity(Enum):
    """Severity/importance of changes."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(Enum):
    """Status of alerts."""

    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


@dataclass
class CompanyChange:
    """A detected change for a company."""

    change_id: str
    company_name: str
    change_type: ChangeType
    severity: ChangeSeverity
    title: str
    description: str
    source_url: str | None = None
    detected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "change_id": self.change_id,
            "company_name": self.company_name,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "source_url": self.source_url,
            "detected_at": self.detected_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Alert:
    """An alert for a company change."""

    alert_id: str
    change_id: str
    company_name: str
    status: AlertStatus
    message: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: datetime | None = None
    acknowledged_at: datetime | None = None


@dataclass
class MonitoringConfig:
    """Configuration for company monitoring."""

    company_name: str
    check_interval_minutes: int = 60
    change_types: list[ChangeType] = field(default_factory=lambda: list(ChangeType))
    min_severity: ChangeSeverity = ChangeSeverity.LOW
    webhook_url: str | None = None
    email_recipients: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class ContentSnapshot:
    """A snapshot of company content at a point in time."""

    snapshot_id: str
    company_name: str
    content_hash: str
    content_summary: str
    captured_at: datetime = field(default_factory=datetime.utcnow)
    source_urls: list[str] = field(default_factory=list)


@dataclass
class TrendPoint:
    """A data point for trend analysis."""

    timestamp: datetime
    metric_name: str
    value: float
    company_name: str


class CompanyMonitor:
    """Monitors companies for changes and updates."""

    # Keywords for change type detection
    CHANGE_KEYWORDS = {
        ChangeType.NEWS: ["announced", "news", "press release", "statement"],
        ChangeType.LEADERSHIP: ["ceo", "cfo", "appointed", "resigned", "executive", "board"],
        ChangeType.FINANCIAL: ["revenue", "profit", "earnings", "quarterly", "fiscal", "stock"],
        ChangeType.PRODUCT: ["launch", "product", "release", "feature", "update", "version"],
        ChangeType.PARTNERSHIP: ["partner", "collaboration", "alliance", "joint venture"],
        ChangeType.LEGAL: ["lawsuit", "legal", "court", "settlement", "regulatory"],
        ChangeType.ACQUISITION: ["acquire", "merger", "acquisition", "buyout", "takeover"],
        ChangeType.EXPANSION: ["expand", "new market", "new office", "growth", "hiring"],
        ChangeType.LAYOFF: ["layoff", "restructuring", "downsizing", "job cuts"],
    }

    # Severity keywords
    SEVERITY_KEYWORDS = {
        ChangeSeverity.CRITICAL: ["urgent", "critical", "breaking", "major", "significant"],
        ChangeSeverity.HIGH: ["important", "notable", "key", "substantial"],
        ChangeSeverity.MEDIUM: ["update", "change", "new"],
        ChangeSeverity.LOW: ["minor", "small", "slight"],
    }

    def __init__(self, db_path: str | None = None):
        """Initialize the monitor."""
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        # Always use persistent connection to avoid connection leaks
        self._persistent_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()
        self._alert_handlers: list[Callable[[Alert], None]] = []

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return self._persistent_conn

    def close(self) -> None:
        """Close the database connection."""
        if self._persistent_conn is not None:
            self._persistent_conn.close()
            self._persistent_conn = None

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute query."""
        conn = self._get_connection()
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor

    def _fetchone(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        """Fetch one row."""
        result = self._get_connection().execute(query, params).fetchone()
        return result  # type: ignore[no-any-return]

    def _fetchall(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all rows."""
        return self._get_connection().execute(query, params).fetchall()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS changes (
                change_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                change_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                source_url TEXT,
                detected_at TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                change_id TEXT NOT NULL,
                company_name TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                acknowledged_at TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_summary TEXT,
                captured_at TEXT NOT NULL,
                source_urls_json TEXT
            );

            CREATE TABLE IF NOT EXISTS monitoring_configs (
                company_name TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_changes_company ON changes(company_name);
            CREATE INDEX IF NOT EXISTS idx_alerts_company ON alerts(company_name);
            CREATE INDEX IF NOT EXISTS idx_snapshots_company ON snapshots(company_name);
        """)
        conn.commit()

    def add_monitoring(self, config: MonitoringConfig) -> None:
        """Add or update monitoring configuration."""
        now = datetime.utcnow().isoformat()
        config_json = json.dumps(
            {
                "check_interval_minutes": config.check_interval_minutes,
                "change_types": [ct.value for ct in config.change_types],
                "min_severity": config.min_severity.value,
                "webhook_url": config.webhook_url,
                "email_recipients": config.email_recipients,
                "enabled": config.enabled,
            }
        )

        with self._lock:
            existing = self._fetchone(
                "SELECT company_name FROM monitoring_configs WHERE company_name = ?",
                (config.company_name,),
            )
            if existing:
                self._execute(
                    "UPDATE monitoring_configs SET config_json = ?, updated_at = ? WHERE company_name = ?",
                    (config_json, now, config.company_name),
                )
            else:
                self._execute(
                    "INSERT INTO monitoring_configs (company_name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (config.company_name, config_json, now, now),
                )

    def get_monitoring(self, company_name: str) -> MonitoringConfig | None:
        """Get monitoring configuration for a company."""
        row = self._fetchone(
            "SELECT config_json FROM monitoring_configs WHERE company_name = ?",
            (company_name,),
        )
        if not row:
            return None

        data = json.loads(row["config_json"])
        return MonitoringConfig(
            company_name=company_name,
            check_interval_minutes=data.get("check_interval_minutes", 60),
            change_types=[ChangeType(ct) for ct in data.get("change_types", [])],
            min_severity=ChangeSeverity(data.get("min_severity", "low")),
            webhook_url=data.get("webhook_url"),
            email_recipients=data.get("email_recipients", []),
            enabled=data.get("enabled", True),
        )

    def remove_monitoring(self, company_name: str) -> bool:
        """Remove monitoring for a company."""
        with self._lock:
            result = self._execute(
                "DELETE FROM monitoring_configs WHERE company_name = ?",
                (company_name,),
            )
            return result.rowcount > 0

    def detect_changes(
        self,
        company_name: str,
        new_content: str,
        source_url: str | None = None,
    ) -> list[CompanyChange]:
        """Detect changes in company content.

        Args:
            company_name: Company name
            new_content: New content to analyze
            source_url: Source URL

        Returns:
            List of detected changes
        """
        changes: list[CompanyChange] = []
        content_lower = new_content.lower()

        # Get previous snapshot
        prev_snapshot = self._get_latest_snapshot(company_name)
        new_hash = self._hash_content(new_content)

        # If content hasn't changed, no changes to detect
        if prev_snapshot and prev_snapshot.content_hash == new_hash:
            return []

        # Detect change types
        for change_type, keywords in self.CHANGE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content_lower:
                    # Extract relevant sentence
                    title, description = self._extract_change_context(new_content, keyword)
                    if title:
                        severity = self._determine_severity(description)
                        change = CompanyChange(
                            change_id=self._generate_id(company_name, title),
                            company_name=company_name,
                            change_type=change_type,
                            severity=severity,
                            title=title,
                            description=description,
                            source_url=source_url,
                        )
                        changes.append(change)
                    break  # One change per type

        # Save snapshot
        self._save_snapshot(company_name, new_content, new_hash, source_url)

        # Save changes
        for change in changes:
            self._save_change(change)

        return changes

    def get_changes(
        self,
        company_name: str,
        since: datetime | None = None,
        change_type: ChangeType | None = None,
        min_severity: ChangeSeverity | None = None,
        limit: int = 100,
    ) -> list[CompanyChange]:
        """Get changes for a company.

        Args:
            company_name: Company name
            since: Only changes after this time
            change_type: Filter by change type
            min_severity: Minimum severity level
            limit: Maximum results

        Returns:
            List of changes
        """
        query = "SELECT * FROM changes WHERE company_name = ?"
        params: list[Any] = [company_name]

        if since:
            query += " AND detected_at >= ?"
            params.append(since.isoformat())

        if change_type:
            query += " AND change_type = ?"
            params.append(change_type.value)

        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)

        rows = self._fetchall(query, tuple(params))
        changes = [self._row_to_change(row) for row in rows]

        # Filter by severity if specified
        if min_severity:
            severity_order = {
                ChangeSeverity.CRITICAL: 0,
                ChangeSeverity.HIGH: 1,
                ChangeSeverity.MEDIUM: 2,
                ChangeSeverity.LOW: 3,
                ChangeSeverity.INFO: 4,
            }
            min_order = severity_order.get(min_severity, 4)
            changes = [c for c in changes if severity_order.get(c.severity, 4) <= min_order]

        return changes

    def create_alert(self, change: CompanyChange) -> Alert:
        """Create an alert for a change."""
        alert = Alert(
            alert_id=self._generate_id(change.company_name, str(time.time())),
            change_id=change.change_id,
            company_name=change.company_name,
            status=AlertStatus.PENDING,
            message=f"[{change.severity.value.upper()}] {change.title}",
        )

        self._execute(
            """INSERT INTO alerts
            (alert_id, change_id, company_name, status, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                alert.alert_id,
                alert.change_id,
                alert.company_name,
                alert.status.value,
                alert.message,
                alert.created_at.isoformat(),
            ),
        )

        # Notify handlers
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.warning(
                    "Alert handler %s failed: %s", getattr(handler, "__name__", handler), e
                )

        return alert

    def get_alerts(
        self,
        company_name: str | None = None,
        status: AlertStatus | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Get alerts."""
        query = "SELECT * FROM alerts WHERE 1=1"
        params: list[Any] = []

        if company_name:
            query += " AND company_name = ?"
            params.append(company_name)

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._fetchall(query, tuple(params))
        return [self._row_to_alert(row) for row in rows]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        now = datetime.utcnow().isoformat()
        result = self._execute(
            "UPDATE alerts SET status = ?, acknowledged_at = ? WHERE alert_id = ?",
            (AlertStatus.ACKNOWLEDGED.value, now, alert_id),
        )
        return result.rowcount > 0

    def dismiss_alert(self, alert_id: str) -> bool:
        """Dismiss an alert."""
        result = self._execute(
            "UPDATE alerts SET status = ? WHERE alert_id = ?",
            (AlertStatus.DISMISSED.value, alert_id),
        )
        return result.rowcount > 0

    def register_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """Register a handler for new alerts."""
        self._alert_handlers.append(handler)

    def get_monitored_companies(self) -> list[str]:
        """Get list of monitored companies."""
        rows = self._fetchall(
            "SELECT company_name FROM monitoring_configs WHERE json_extract(config_json, '$.enabled') = 1"
        )
        return [row["company_name"] for row in rows]

    def get_change_summary(
        self,
        company_name: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get summary of changes over a period."""
        since = datetime.utcnow() - timedelta(days=days)
        changes = self.get_changes(company_name, since=since)

        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}

        for change in changes:
            by_type[change.change_type.value] = by_type.get(change.change_type.value, 0) + 1
            by_severity[change.severity.value] = by_severity.get(change.severity.value, 0) + 1

        return {
            "company_name": company_name,
            "period_days": days,
            "total_changes": len(changes),
            "by_type": by_type,
            "by_severity": by_severity,
            "latest_change": changes[0].to_dict() if changes else None,
        }

    def _get_latest_snapshot(self, company_name: str) -> ContentSnapshot | None:
        """Get the latest snapshot for a company."""
        row = self._fetchone(
            "SELECT * FROM snapshots WHERE company_name = ? ORDER BY captured_at DESC LIMIT 1",
            (company_name,),
        )
        if not row:
            return None

        return ContentSnapshot(
            snapshot_id=row["snapshot_id"],
            company_name=row["company_name"],
            content_hash=row["content_hash"],
            content_summary=row["content_summary"] or "",
            captured_at=datetime.fromisoformat(row["captured_at"]),
            source_urls=json.loads(row["source_urls_json"] or "[]"),
        )

    def _save_snapshot(
        self,
        company_name: str,
        content: str,
        content_hash: str,
        source_url: str | None,
    ) -> None:
        """Save a content snapshot."""
        snapshot_id = self._generate_id(company_name, content_hash)
        summary = content[:500] if content else ""
        source_urls = [source_url] if source_url else []

        self._execute(
            """INSERT INTO snapshots
            (snapshot_id, company_name, content_hash, content_summary, captured_at, source_urls_json)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                company_name,
                content_hash,
                summary,
                datetime.utcnow().isoformat(),
                json.dumps(source_urls),
            ),
        )

    def _save_change(self, change: CompanyChange) -> None:
        """Save a change to the database."""
        self._execute(
            """INSERT OR IGNORE INTO changes
            (change_id, company_name, change_type, severity, title, description,
             source_url, detected_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                change.change_id,
                change.company_name,
                change.change_type.value,
                change.severity.value,
                change.title,
                change.description,
                change.source_url,
                change.detected_at.isoformat(),
                json.dumps(change.metadata),
            ),
        )

    def _extract_change_context(
        self,
        content: str,
        keyword: str,
    ) -> tuple[str, str]:
        """Extract title and description around a keyword."""
        sentences = content.replace("\n", " ").split(".")
        for idx, sentence in enumerate(sentences):
            if keyword in sentence.lower():
                title = sentence.strip()[:100]
                # Get surrounding context
                start = max(0, idx - 1)
                end = min(len(sentences), idx + 2)
                description = ". ".join(sentences[start:end]).strip()
                return title, description[:500]
        return "", ""

    def _determine_severity(self, text: str) -> ChangeSeverity:
        """Determine severity from text."""
        text_lower = text.lower()
        for severity, keywords in self.SEVERITY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return severity
        return ChangeSeverity.MEDIUM

    def _hash_content(self, content: str) -> str:
        """Generate hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _generate_id(self, *parts: str) -> str:
        """Generate a unique ID."""
        data = ":".join(parts) + str(time.time_ns())
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _row_to_change(self, row: sqlite3.Row) -> CompanyChange:
        """Convert row to CompanyChange."""
        return CompanyChange(
            change_id=row["change_id"],
            company_name=row["company_name"],
            change_type=ChangeType(row["change_type"]),
            severity=ChangeSeverity(row["severity"]),
            title=row["title"],
            description=row["description"] or "",
            source_url=row["source_url"],
            detected_at=datetime.fromisoformat(row["detected_at"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def _row_to_alert(self, row: sqlite3.Row) -> Alert:
        """Convert row to Alert."""
        return Alert(
            alert_id=row["alert_id"],
            change_id=row["change_id"],
            company_name=row["company_name"],
            status=AlertStatus(row["status"]),
            message=row["message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
            acknowledged_at=datetime.fromisoformat(row["acknowledged_at"])
            if row["acknowledged_at"]
            else None,
        )


# Global instance
_monitor: CompanyMonitor | None = None
_monitor_lock = threading.Lock()


def get_company_monitor(db_path: str | None = None) -> CompanyMonitor:
    """Get the global company monitor instance."""
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = CompanyMonitor(db_path)
        return _monitor


def reset_company_monitor() -> None:
    """Reset the global monitor (for testing)."""
    global _monitor
    with _monitor_lock:
        _monitor = None


# Convenience functions
def add_monitoring(config: MonitoringConfig) -> None:
    """Add monitoring for a company."""
    get_company_monitor().add_monitoring(config)


def detect_changes(
    company_name: str,
    content: str,
    source_url: str | None = None,
) -> list[CompanyChange]:
    """Detect changes in company content."""
    return get_company_monitor().detect_changes(company_name, content, source_url)


def get_changes(
    company_name: str,
    since: datetime | None = None,
    change_type: ChangeType | None = None,
) -> list[CompanyChange]:
    """Get changes for a company."""
    return get_company_monitor().get_changes(company_name, since, change_type)


def create_alert(change: CompanyChange) -> Alert:
    """Create an alert for a change."""
    return get_company_monitor().create_alert(change)


def get_alerts(
    company_name: str | None = None,
    status: AlertStatus | None = None,
) -> list[Alert]:
    """Get alerts."""
    return get_company_monitor().get_alerts(company_name, status)


def get_change_summary(company_name: str, days: int = 30) -> dict[str, Any]:
    """Get change summary for a company."""
    return get_company_monitor().get_change_summary(company_name, days)
