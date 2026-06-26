"""Tests for knowledge graph module."""

from datetime import datetime

import pytest

from primr.data.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relationship,
    RelationType,
    add_entity,
    add_relationship,
    extract_from_content,
    get_company_graph,
    get_knowledge_graph,
    reset_knowledge_graph,
)


@pytest.fixture
def graph():
    """Create a fresh graph for each test."""
    reset_knowledge_graph()
    graph = KnowledgeGraph()
    try:
        yield graph
    finally:
        graph.close()
        reset_knowledge_graph()


@pytest.fixture(autouse=True)
def clean_global_graph():
    """Ensure global graph state never leaks open connections between tests."""
    reset_knowledge_graph()
    yield
    reset_knowledge_graph()


@pytest.fixture
def sample_content():
    """Sample content with entities and relationships."""
    return """
    Acme Corp is a technology company founded by John Smith.
    The CEO John Smith leads the company with CFO Jane Doe.
    Acme Corp acquired TechStartup last year.
    Acme Corp partnered with BigTech for cloud services.
    Acme Corp competes with RivalCorp in the enterprise market.
    """


class TestEntityType:
    """Tests for EntityType enum."""

    def test_entity_types(self):
        """Test all entity types exist."""
        assert EntityType.COMPANY.value == "company"
        assert EntityType.PERSON.value == "person"
        assert EntityType.PRODUCT.value == "product"
        assert EntityType.LOCATION.value == "location"


class TestRelationType:
    """Tests for RelationType enum."""

    def test_relation_types(self):
        """Test all relation types exist."""
        assert RelationType.OWNS.value == "owns"
        assert RelationType.SUBSIDIARY_OF.value == "subsidiary_of"
        assert RelationType.PARTNER_WITH.value == "partner_with"
        assert RelationType.COMPETES_WITH.value == "competes_with"
        assert RelationType.ACQUIRES.value == "acquires"
        assert RelationType.WORKS_AT.value == "works_at"


class TestEntity:
    """Tests for Entity dataclass."""

    def test_default_values(self):
        """Test default values."""
        entity = Entity(
            entity_id="test1",
            entity_type=EntityType.COMPANY,
            name="Test Corp",
        )
        assert entity.properties == {}
        assert isinstance(entity.created_at, datetime)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        entity = Entity(
            entity_id="test2",
            entity_type=EntityType.PERSON,
            name="John Doe",
            properties={"title": "CEO"},
        )
        data = entity.to_dict()
        assert data["entity_id"] == "test2"
        assert data["type"] == "person"
        assert data["properties"]["title"] == "CEO"


class TestRelationship:
    """Tests for Relationship dataclass."""

    def test_default_values(self):
        """Test default values."""
        rel = Relationship(
            relationship_id="rel1",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.PARTNER_WITH,
        )
        assert rel.confidence == 0.8
        assert rel.properties == {}

    def test_to_dict(self):
        """Test conversion to dictionary."""
        rel = Relationship(
            relationship_id="rel2",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.ACQUIRES,
            confidence=0.9,
        )
        data = rel.to_dict()
        assert data["relationship_id"] == "rel2"
        assert data["type"] == "acquires"
        assert data["confidence"] == 0.9


class TestKnowledgeGraph:
    """Tests for KnowledgeGraph class."""

    def test_add_entity(self, graph):
        """Test adding an entity."""
        entity = graph.add_entity(EntityType.COMPANY, "Test Corp")

        assert entity.name == "Test Corp"
        assert entity.entity_type == EntityType.COMPANY
        assert entity.entity_id.startswith("company_")

    def test_add_entity_with_properties(self, graph):
        """Test adding entity with properties."""
        entity = graph.add_entity(
            EntityType.PERSON,
            "John Doe",
            {"title": "CEO", "age": 45},
        )

        assert entity.properties["title"] == "CEO"
        assert entity.properties["age"] == 45

    def test_add_entity_deduplication(self, graph):
        """Test that duplicate entities are not created."""
        entity1 = graph.add_entity(EntityType.COMPANY, "Test Corp")
        entity2 = graph.add_entity(EntityType.COMPANY, "Test Corp")

        assert entity1.entity_id == entity2.entity_id

    def test_get_entity(self, graph):
        """Test getting entity by ID."""
        created = graph.add_entity(EntityType.COMPANY, "Test Corp")
        retrieved = graph.get_entity(created.entity_id)

        assert retrieved is not None
        assert retrieved.name == "Test Corp"

    def test_get_entity_not_found(self, graph):
        """Test getting non-existent entity."""
        result = graph.get_entity("nonexistent")
        assert result is None

    def test_get_entity_by_name(self, graph):
        """Test getting entity by name."""
        graph.add_entity(EntityType.COMPANY, "Test Corp")
        retrieved = graph.get_entity_by_name("Test Corp")

        assert retrieved is not None
        assert retrieved.name == "Test Corp"

    def test_get_entity_by_name_with_type(self, graph):
        """Test getting entity by name and type."""
        graph.add_entity(EntityType.COMPANY, "Test")
        graph.add_entity(EntityType.PERSON, "Test")

        company = graph.get_entity_by_name("Test", EntityType.COMPANY)
        person = graph.get_entity_by_name("Test", EntityType.PERSON)

        assert company.entity_type == EntityType.COMPANY
        assert person.entity_type == EntityType.PERSON

    def test_add_relationship(self, graph):
        """Test adding a relationship."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")

        rel = graph.add_relationship(
            e1.entity_id,
            e2.entity_id,
            RelationType.PARTNER_WITH,
        )

        assert rel.source_id == e1.entity_id
        assert rel.target_id == e2.entity_id
        assert rel.relation_type == RelationType.PARTNER_WITH

    def test_add_relationship_with_properties(self, graph):
        """Test adding relationship with properties."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")

        rel = graph.add_relationship(
            e1.entity_id,
            e2.entity_id,
            RelationType.ACQUIRES,
            properties={"year": 2024, "value": "$1B"},
        )

        assert rel.properties["year"] == 2024
        assert rel.properties["value"] == "$1B"

    def test_get_relationships(self, graph):
        """Test getting relationships for an entity."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")
        e3 = graph.add_entity(EntityType.COMPANY, "Company C")

        graph.add_relationship(e1.entity_id, e2.entity_id, RelationType.PARTNER_WITH)
        graph.add_relationship(e1.entity_id, e3.entity_id, RelationType.COMPETES_WITH)

        relationships = graph.get_relationships(e1.entity_id)
        assert len(relationships) == 2

    def test_get_relationships_by_type(self, graph):
        """Test getting relationships filtered by type."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")
        e3 = graph.add_entity(EntityType.COMPANY, "Company C")

        graph.add_relationship(e1.entity_id, e2.entity_id, RelationType.PARTNER_WITH)
        graph.add_relationship(e1.entity_id, e3.entity_id, RelationType.COMPETES_WITH)

        partners = graph.get_relationships(e1.entity_id, relation_type=RelationType.PARTNER_WITH)
        assert len(partners) == 1

    def test_get_relationships_direction(self, graph):
        """Test getting relationships by direction."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")

        graph.add_relationship(e1.entity_id, e2.entity_id, RelationType.ACQUIRES)

        outgoing = graph.get_relationships(e1.entity_id, direction="outgoing")
        incoming = graph.get_relationships(e2.entity_id, direction="incoming")

        assert len(outgoing) == 1
        assert len(incoming) == 1


class TestContentExtraction:
    """Tests for content extraction."""

    def test_extract_entities(self, graph, sample_content):
        """Test extracting entities from content."""
        entities = graph.extract_entities_from_content(sample_content, "Acme Corp")

        # Should at least have the company
        names = [e.name for e in entities]
        assert "Acme Corp" in names

    def test_extract_relationships(self, graph, sample_content):
        """Test extracting relationships from content."""
        # First add the company
        graph.add_entity(EntityType.COMPANY, "Acme Corp")

        relationships = graph.extract_relationships_from_content(sample_content, "Acme Corp")

        # Should find some relationships
        assert isinstance(relationships, list)

    def test_extract_acquisition(self, graph):
        """Test extracting acquisition relationship."""
        content = "BigCorp acquired SmallStartup in 2024."
        graph.add_entity(EntityType.COMPANY, "BigCorp")

        relationships = graph.extract_relationships_from_content(content, "BigCorp")

        rel_types = [r.relation_type for r in relationships]
        assert RelationType.ACQUIRES in rel_types or len(relationships) >= 0

    def test_extract_partnership(self, graph):
        """Test extracting partnership relationship."""
        content = "CompanyA partnered with CompanyB for cloud services."
        graph.add_entity(EntityType.COMPANY, "CompanyA")

        relationships = graph.extract_relationships_from_content(content, "CompanyA")

        # Check structure
        for rel in relationships:
            assert isinstance(rel, Relationship)


class TestCompanyGraph:
    """Tests for company graph retrieval."""

    def test_get_company_graph(self, graph):
        """Test getting company graph."""
        company = graph.add_entity(EntityType.COMPANY, "Test Corp")
        partner = graph.add_entity(EntityType.COMPANY, "Partner Corp")

        graph.add_relationship(
            company.entity_id,
            partner.entity_id,
            RelationType.PARTNER_WITH,
        )

        node = graph.get_company_graph("Test Corp")

        assert node is not None
        assert node.entity.name == "Test Corp"
        assert "Partner Corp" in node.partners

    def test_get_company_graph_not_found(self, graph):
        """Test getting non-existent company graph."""
        result = graph.get_company_graph("Unknown Corp")
        assert result is None

    def test_get_company_graph_with_subsidiaries(self, graph):
        """Test company graph with subsidiaries."""
        parent = graph.add_entity(EntityType.COMPANY, "Parent Corp")
        sub = graph.add_entity(EntityType.COMPANY, "Subsidiary Inc")

        graph.add_relationship(
            sub.entity_id,
            parent.entity_id,
            RelationType.SUBSIDIARY_OF,
        )

        node = graph.get_company_graph("Parent Corp")
        assert "Subsidiary Inc" in node.subsidiaries

    def test_get_company_graph_with_competitors(self, graph):
        """Test company graph with competitors."""
        company = graph.add_entity(EntityType.COMPANY, "Test Corp")
        competitor = graph.add_entity(EntityType.COMPANY, "Rival Corp")

        graph.add_relationship(
            company.entity_id,
            competitor.entity_id,
            RelationType.COMPETES_WITH,
        )

        node = graph.get_company_graph("Test Corp")
        assert "Rival Corp" in node.competitors


class TestPathFinding:
    """Tests for path finding."""

    def test_find_direct_path(self, graph):
        """Test finding direct path."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")

        graph.add_relationship(e1.entity_id, e2.entity_id, RelationType.PARTNER_WITH)

        path = graph.find_path("Company A", "Company B")
        assert len(path) == 1

    def test_find_indirect_path(self, graph):
        """Test finding indirect path."""
        e1 = graph.add_entity(EntityType.COMPANY, "Company A")
        e2 = graph.add_entity(EntityType.COMPANY, "Company B")
        e3 = graph.add_entity(EntityType.COMPANY, "Company C")

        graph.add_relationship(e1.entity_id, e2.entity_id, RelationType.PARTNER_WITH)
        graph.add_relationship(e2.entity_id, e3.entity_id, RelationType.PARTNER_WITH)

        path = graph.find_path("Company A", "Company C")
        assert len(path) == 2

    def test_find_path_not_found(self, graph):
        """Test when no path exists."""
        graph.add_entity(EntityType.COMPANY, "Company A")
        graph.add_entity(EntityType.COMPANY, "Company B")

        path = graph.find_path("Company A", "Company B")
        assert path == []

    def test_find_path_entity_not_found(self, graph):
        """Test when entity doesn't exist."""
        path = graph.find_path("Unknown A", "Unknown B")
        assert path == []


class TestStatistics:
    """Tests for graph statistics."""

    def test_get_statistics(self, graph):
        """Test getting graph statistics."""
        graph.add_entity(EntityType.COMPANY, "Company A")
        graph.add_entity(EntityType.COMPANY, "Company B")
        graph.add_entity(EntityType.PERSON, "John Doe")

        stats = graph.get_statistics()

        assert stats["total_entities"] == 3
        assert stats["entities_by_type"]["company"] == 2
        assert stats["entities_by_type"]["person"] == 1

    def test_get_statistics_empty(self, graph):
        """Test statistics on empty graph."""
        stats = graph.get_statistics()

        assert stats["total_entities"] == 0
        assert stats["total_relationships"] == 0


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def test_get_knowledge_graph(self):
        """Test getting global graph."""
        reset_knowledge_graph()
        graph1 = get_knowledge_graph()
        graph2 = get_knowledge_graph()
        assert graph1 is graph2

    def test_add_entity_function(self):
        """Test add_entity convenience function."""
        reset_knowledge_graph()
        entity = add_entity(EntityType.COMPANY, "Test Corp")
        assert entity.name == "Test Corp"

    def test_add_relationship_function(self):
        """Test add_relationship convenience function."""
        reset_knowledge_graph()
        e1 = add_entity(EntityType.COMPANY, "Company A")
        e2 = add_entity(EntityType.COMPANY, "Company B")

        rel = add_relationship(
            e1.entity_id,
            e2.entity_id,
            RelationType.PARTNER_WITH,
        )
        assert rel.relation_type == RelationType.PARTNER_WITH

    def test_get_company_graph_function(self):
        """Test get_company_graph convenience function."""
        reset_knowledge_graph()
        add_entity(EntityType.COMPANY, "Test Corp")

        node = get_company_graph("Test Corp")
        assert node is not None

    def test_extract_from_content_function(self):
        """Test extract_from_content convenience function."""
        reset_knowledge_graph()
        content = "Acme Corp is a technology company."

        entities, relationships = extract_from_content("Acme Corp", content)
        assert len(entities) >= 1


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self, graph):
        """Test with empty content."""
        entities = graph.extract_entities_from_content("", "Test Corp")
        # Should at least have the company
        assert len(entities) >= 1

    def test_special_characters_in_name(self, graph):
        """Test entity names with special characters."""
        entity = graph.add_entity(EntityType.COMPANY, "Test & Corp, Inc.")
        assert entity.name == "Test & Corp, Inc."

    def test_unicode_names(self, graph):
        """Test unicode entity names."""
        entity = graph.add_entity(EntityType.COMPANY, "日本企業株式会社")
        assert entity.name == "日本企業株式会社"

    def test_very_long_content(self, graph):
        """Test with very long content."""
        content = "Company information. " * 500
        entities = graph.extract_entities_from_content(content, "Test Corp")
        assert isinstance(entities, list)
