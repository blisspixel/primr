"""
Knowledge graph module.

Builds and queries company relationship graphs, tracks executives, and maps connections.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EntityType(Enum):
    """Types of entities in the knowledge graph."""
    COMPANY = "company"
    PERSON = "person"
    PRODUCT = "product"
    LOCATION = "location"
    EVENT = "event"


class RelationType(Enum):
    """Types of relationships between entities."""
    OWNS = "owns"
    SUBSIDIARY_OF = "subsidiary_of"
    PARTNER_WITH = "partner_with"
    COMPETES_WITH = "competes_with"
    SUPPLIES_TO = "supplies_to"
    ACQUIRES = "acquires"
    INVESTS_IN = "invests_in"
    WORKS_AT = "works_at"
    FOUNDED = "founded"
    LOCATED_IN = "located_in"
    PRODUCES = "produces"


@dataclass
class Entity:
    """An entity in the knowledge graph."""
    entity_id: str
    entity_type: EntityType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "type": self.entity_type.value,
            "name": self.name,
            "properties": self.properties,
        }


@dataclass
class Relationship:
    """A relationship between two entities."""
    relationship_id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    source_url: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "relationship_id": self.relationship_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.relation_type.value,
            "properties": self.properties,
            "confidence": self.confidence,
        }


@dataclass
class Executive:
    """An executive/person entity with role information."""
    person_id: str
    name: str
    title: str
    company_id: str
    company_name: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    is_current: bool = True
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompanyNode:
    """A company node with its relationships."""
    entity: Entity
    executives: list[Executive] = field(default_factory=list)
    subsidiaries: list[str] = field(default_factory=list)
    parent_company: str | None = None
    partners: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    suppliers: list[str] = field(default_factory=list)
    customers: list[str] = field(default_factory=list)


class KnowledgeGraph:
    """Builds and queries company knowledge graphs."""

    # Executive title patterns
    EXECUTIVE_PATTERNS = [
        (r"(?:CEO|Chief Executive Officer)", "CEO"),
        (r"(?:CFO|Chief Financial Officer)", "CFO"),
        (r"(?:CTO|Chief Technology Officer)", "CTO"),
        (r"(?:COO|Chief Operating Officer)", "COO"),
        (r"(?:CMO|Chief Marketing Officer)", "CMO"),
        (r"(?:President)", "President"),
        (r"(?:Chairman|Chairwoman|Chair)", "Chairman"),
        (r"(?:Vice President|VP)", "Vice President"),
        (r"(?:Director)", "Director"),
        (r"(?:Founder|Co-Founder)", "Founder"),
    ]

    # Relationship patterns
    RELATIONSHIP_PATTERNS = {
        RelationType.SUBSIDIARY_OF: [
            r"(\w+(?:\s+\w+)*)\s+is\s+(?:a\s+)?subsidiary\s+of\s+(\w+(?:\s+\w+)*)",
            r"(\w+(?:\s+\w+)*)\s+(?:is\s+)?owned\s+by\s+(\w+(?:\s+\w+)*)",
        ],
        RelationType.PARTNER_WITH: [
            r"(\w+(?:\s+\w+)*)\s+partner(?:ed|s)?\s+with\s+(\w+(?:\s+\w+)*)",
            r"partnership\s+between\s+(\w+(?:\s+\w+)*)\s+and\s+(\w+(?:\s+\w+)*)",
        ],
        RelationType.ACQUIRES: [
            r"(\w+(?:\s+\w+)*)\s+acquir(?:ed|es)\s+(\w+(?:\s+\w+)*)",
            r"(\w+(?:\s+\w+)*)\s+bought\s+(\w+(?:\s+\w+)*)",
        ],
        RelationType.COMPETES_WITH: [
            r"(\w+(?:\s+\w+)*)\s+competes?\s+with\s+(\w+(?:\s+\w+)*)",
            r"(\w+(?:\s+\w+)*)\s+(?:is\s+)?(?:a\s+)?competitor\s+(?:of|to)\s+(\w+(?:\s+\w+)*)",
        ],
    }

    def __init__(self, db_path: str | None = None):
        """Initialize the knowledge graph."""
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._persistent_conn: sqlite3.Connection | None = None
        if self._db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()
        self._id_counter = 0

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

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
            CREATE TABLE IF NOT EXISTS entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                properties_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relationships (
                relationship_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                properties_json TEXT,
                confidence REAL DEFAULT 0.8,
                source_url TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES entities(entity_id),
                FOREIGN KEY (target_id) REFERENCES entities(entity_id)
            );

            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id);
            CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_id);
            CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(relation_type);
        """)
        conn.commit()

    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID."""
        with self._lock:
            self._id_counter += 1
            return f"{prefix}_{self._id_counter}"


    def add_entity(
        self,
        entity_type: EntityType,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> Entity:
        """Add an entity to the graph.

        Args:
            entity_type: Type of entity
            name: Entity name
            properties: Additional properties

        Returns:
            Created entity
        """
        # Check if entity already exists
        existing = self.get_entity_by_name(name, entity_type)
        if existing:
            return existing

        entity_id = self._generate_id(entity_type.value)
        now = datetime.utcnow()

        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
            properties=properties or {},
            created_at=now,
            updated_at=now,
        )

        self._execute(
            """INSERT INTO entities
            (entity_id, entity_type, name, properties_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (entity_id, entity_type.value, name, json.dumps(entity.properties),
             now.isoformat(), now.isoformat()),
        )

        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get an entity by ID."""
        row = self._fetchone(
            "SELECT * FROM entities WHERE entity_id = ?",
            (entity_id,),
        )
        return self._row_to_entity(row) if row else None

    def get_entity_by_name(
        self,
        name: str,
        entity_type: EntityType | None = None,
    ) -> Entity | None:
        """Get an entity by name."""
        if entity_type:
            row = self._fetchone(
                "SELECT * FROM entities WHERE name = ? AND entity_type = ?",
                (name, entity_type.value),
            )
        else:
            row = self._fetchone(
                "SELECT * FROM entities WHERE name = ?",
                (name,),
            )
        return self._row_to_entity(row) if row else None

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        properties: dict[str, Any] | None = None,
        confidence: float = 0.8,
        source_url: str | None = None,
    ) -> Relationship:
        """Add a relationship between entities.

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relation_type: Type of relationship
            properties: Additional properties
            confidence: Confidence score
            source_url: Source URL

        Returns:
            Created relationship
        """
        relationship_id = self._generate_id("rel")
        now = datetime.utcnow()

        relationship = Relationship(
            relationship_id=relationship_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties or {},
            confidence=confidence,
            source_url=source_url,
            created_at=now,
        )

        self._execute(
            """INSERT INTO relationships
            (relationship_id, source_id, target_id, relation_type, properties_json,
             confidence, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (relationship_id, source_id, target_id, relation_type.value,
             json.dumps(relationship.properties), confidence, source_url,
             now.isoformat()),
        )

        return relationship

    def get_relationships(
        self,
        entity_id: str,
        relation_type: RelationType | None = None,
        direction: str = "both",
    ) -> list[Relationship]:
        """Get relationships for an entity.

        Args:
            entity_id: Entity ID
            relation_type: Filter by type
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of relationships
        """
        relationships: list[Relationship] = []

        if direction in ("outgoing", "both"):
            query = "SELECT * FROM relationships WHERE source_id = ?"
            params: list[Any] = [entity_id]
            if relation_type:
                query += " AND relation_type = ?"
                params.append(relation_type.value)
            rows = self._fetchall(query, tuple(params))
            relationships.extend(self._row_to_relationship(r) for r in rows)

        if direction in ("incoming", "both"):
            query = "SELECT * FROM relationships WHERE target_id = ?"
            params = [entity_id]
            if relation_type:
                query += " AND relation_type = ?"
                params.append(relation_type.value)
            rows = self._fetchall(query, tuple(params))
            relationships.extend(self._row_to_relationship(r) for r in rows)

        return relationships


    def extract_entities_from_content(
        self,
        content: str,
        company_name: str,
    ) -> list[Entity]:
        """Extract entities from content.

        Args:
            content: Text content
            company_name: Primary company name

        Returns:
            List of extracted entities
        """
        entities: list[Entity] = []

        # Add the primary company
        company = self.add_entity(EntityType.COMPANY, company_name)
        entities.append(company)

        # Extract executives
        for pattern, title in self.EXECUTIVE_PATTERNS:
            # Look for "Name, Title" or "Title Name" patterns
            name_patterns = [
                rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),?\s+{pattern}",
                rf"{pattern}\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            ]
            for name_pattern in name_patterns:
                matches = re.findall(name_pattern, content)
                for match in matches:
                    name = match.strip() if isinstance(match, str) else match
                    if name and len(name) > 3:
                        person = self.add_entity(
                            EntityType.PERSON,
                            name,
                            {"title": title, "company": company_name},
                        )
                        entities.append(person)
                        # Add works_at relationship
                        self.add_relationship(
                            person.entity_id,
                            company.entity_id,
                            RelationType.WORKS_AT,
                            {"title": title},
                        )

        return entities

    def extract_relationships_from_content(
        self,
        content: str,
        company_name: str,
    ) -> list[Relationship]:
        """Extract relationships from content.

        Args:
            content: Text content
            company_name: Primary company name

        Returns:
            List of extracted relationships
        """
        relationships: list[Relationship] = []

        for relation_type, patterns in self.RELATIONSHIP_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if len(match) >= 2:
                        source_name = match[0].strip()
                        target_name = match[1].strip()

                        if len(source_name) > 2 and len(target_name) > 2:
                            # Add entities if they don't exist
                            source = self.add_entity(EntityType.COMPANY, source_name)
                            target = self.add_entity(EntityType.COMPANY, target_name)

                            # Add relationship
                            rel = self.add_relationship(
                                source.entity_id,
                                target.entity_id,
                                relation_type,
                            )
                            relationships.append(rel)

        return relationships

    def get_company_graph(self, company_name: str) -> CompanyNode | None:
        """Get complete company graph node.

        Args:
            company_name: Company name

        Returns:
            Company node with all relationships
        """
        entity = self.get_entity_by_name(company_name, EntityType.COMPANY)
        if not entity:
            return None

        node = CompanyNode(entity=entity)

        # Get all relationships
        relationships = self.get_relationships(entity.entity_id)

        for rel in relationships:
            # Get the other entity
            other_id = rel.target_id if rel.source_id == entity.entity_id else rel.source_id
            other = self.get_entity(other_id)
            if not other:
                continue

            if rel.relation_type == RelationType.SUBSIDIARY_OF:
                if rel.source_id == entity.entity_id:
                    node.parent_company = other.name
                else:
                    node.subsidiaries.append(other.name)
            elif rel.relation_type == RelationType.PARTNER_WITH:
                node.partners.append(other.name)
            elif rel.relation_type == RelationType.COMPETES_WITH:
                node.competitors.append(other.name)
            elif rel.relation_type == RelationType.SUPPLIES_TO:
                if rel.source_id == entity.entity_id:
                    node.customers.append(other.name)
                else:
                    node.suppliers.append(other.name)
            elif rel.relation_type == RelationType.WORKS_AT:
                if other.entity_type == EntityType.PERSON:
                    exec_info = Executive(
                        person_id=other.entity_id,
                        name=other.name,
                        title=other.properties.get("title", ""),
                        company_id=entity.entity_id,
                        company_name=company_name,
                    )
                    node.executives.append(exec_info)

        return node

    def find_path(
        self,
        source_name: str,
        target_name: str,
        max_depth: int = 5,
    ) -> list[tuple[Entity, Relationship]]:
        """Find path between two entities.

        Args:
            source_name: Source entity name
            target_name: Target entity name
            max_depth: Maximum path depth

        Returns:
            List of (entity, relationship) tuples forming the path
        """
        source = self.get_entity_by_name(source_name)
        target = self.get_entity_by_name(target_name)

        if not source or not target:
            return []

        # BFS to find path
        visited: set[str] = set()
        queue: list[tuple[str, list[tuple[Entity, Relationship]]]] = [
            (source.entity_id, [])
        ]

        while queue:
            current_id, path = queue.pop(0)

            if current_id == target.entity_id:
                return path

            if current_id in visited or len(path) >= max_depth:
                continue

            visited.add(current_id)

            relationships = self.get_relationships(current_id)
            for rel in relationships:
                next_id = rel.target_id if rel.source_id == current_id else rel.source_id
                if next_id not in visited:
                    next_entity = self.get_entity(next_id)
                    if next_entity:
                        queue.append((next_id, path + [(next_entity, rel)]))

        return []

    def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        entity_counts = {}
        for entity_type in EntityType:
            row = self._fetchone(
                "SELECT COUNT(*) as count FROM entities WHERE entity_type = ?",
                (entity_type.value,),
            )
            entity_counts[entity_type.value] = row["count"] if row else 0

        rel_counts = {}
        for rel_type in RelationType:
            row = self._fetchone(
                "SELECT COUNT(*) as count FROM relationships WHERE relation_type = ?",
                (rel_type.value,),
            )
            rel_counts[rel_type.value] = row["count"] if row else 0

        total_entities = self._fetchone("SELECT COUNT(*) as count FROM entities")
        total_rels = self._fetchone("SELECT COUNT(*) as count FROM relationships")

        return {
            "total_entities": total_entities["count"] if total_entities else 0,
            "total_relationships": total_rels["count"] if total_rels else 0,
            "entities_by_type": entity_counts,
            "relationships_by_type": rel_counts,
        }

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert row to Entity."""
        return Entity(
            entity_id=row["entity_id"],
            entity_type=EntityType(row["entity_type"]),
            name=row["name"],
            properties=json.loads(row["properties_json"] or "{}"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_relationship(self, row: sqlite3.Row) -> Relationship:
        """Convert row to Relationship."""
        return Relationship(
            relationship_id=row["relationship_id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=RelationType(row["relation_type"]),
            properties=json.loads(row["properties_json"] or "{}"),
            confidence=row["confidence"],
            source_url=row["source_url"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )



# Global instance
_graph: KnowledgeGraph | None = None
_graph_lock = threading.Lock()


def get_knowledge_graph(db_path: str | None = None) -> KnowledgeGraph:
    """Get the global knowledge graph instance."""
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = KnowledgeGraph(db_path)
        return _graph


def reset_knowledge_graph() -> None:
    """Reset the global graph (for testing)."""
    global _graph
    with _graph_lock:
        _graph = None


# Convenience functions
def add_entity(
    entity_type: EntityType,
    name: str,
    properties: dict[str, Any] | None = None,
) -> Entity:
    """Add an entity to the graph."""
    return get_knowledge_graph().add_entity(entity_type, name, properties)


def add_relationship(
    source_id: str,
    target_id: str,
    relation_type: RelationType,
    properties: dict[str, Any] | None = None,
) -> Relationship:
    """Add a relationship between entities."""
    return get_knowledge_graph().add_relationship(
        source_id, target_id, relation_type, properties
    )


def get_company_graph(company_name: str) -> CompanyNode | None:
    """Get company graph node."""
    return get_knowledge_graph().get_company_graph(company_name)


def extract_from_content(company_name: str, content: str) -> tuple[list[Entity], list[Relationship]]:
    """Extract entities and relationships from content."""
    graph = get_knowledge_graph()
    entities = graph.extract_entities_from_content(content, company_name)
    relationships = graph.extract_relationships_from_content(content, company_name)
    return entities, relationships
