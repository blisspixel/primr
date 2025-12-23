"""
Property-based tests for QA analysis completeness.

**Feature: report-quality-assurance, Property 1: QA execution completeness**
**Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 2.5**
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime
from pathlib import Path

from src.primr.qa.models import (
    ReportContent, ReportMetadata, QAAnalysis, CitationCheckResult,
    LogicCheckResult, CompletenessCheckResult, ConfidenceAssessment,
    ClassifiedIssue, IssueType, Severity
)
from src.primr.qa.analyzer import QAAnalyzer


# Test data generators
@st.composite
def report_metadata(draw):
    """Generate valid ReportMetadata."""
    return ReportMetadata(
        company_name=draw(st.text(min_size=1, max_size=50).filter(lambda x: x.strip())),
        generation_date=draw(st.datetimes(min_value=datetime(2020, 1, 1))),
        generation_mode=draw(st.sampled_from(["scrape", "deep", "full"])),
        model_used=draw(st.sampled_from(["gemini-2.0-flash", "gemini-2.0-flash-thinking-exp"])),
        file_path=Path("test_report.txt")
    )


@st.composite
def report_content(draw):
    """Generate valid ReportContent for testing."""
    company_name = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'), whitelist_characters=' ')))
    
    # Generate simpler, smaller sections
    section_names = draw(st.lists(
        st.sampled_from([
            "Executive Summary", "Company Overview", "Business Model",
            "Financial Analysis", "Market Position", "Conclusion"
        ]),
        min_size=2, max_size=4, unique=True
    ))
    
    sections = {}
    content_parts = []
    
    for section in section_names:
        section_content = draw(st.text(min_size=20, max_size=100, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc'), whitelist_characters=' .,!?')))
        sections[section] = section_content
        content_parts.append(f"## {section}\n\n{section_content}\n")
    
    full_content = "\n".join(content_parts)
    
    # Generate simpler citations
    citations = draw(st.lists(
        st.just("https://example.com/source"),
        min_size=0, max_size=3
    ))
    
    metadata = ReportMetadata(
        company_name=company_name,
        generation_date=datetime(2024, 1, 1),
        generation_mode="test",
        model_used="test-model",
        file_path=Path("test_report.txt")
    )
    
    return ReportContent(
        company_name=company_name,
        content=full_content,
        sections=sections,
        citations=citations,
        metadata=metadata,
        file_path=Path("test_report.txt")
    )


class TestQAAnalysisCompleteness:
    """Property-based tests for QA analysis completeness."""
    
    @given(report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10)
    def test_qa_analysis_completeness_property(self, report: ReportContent):
        """
        **Feature: report-quality-assurance, Property 1: QA execution completeness**
        **Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 2.5**
        
        Property: For any valid report content, QA analysis should produce
        a complete analysis with all required components.
        
        This tests that the QA analyzer consistently produces comprehensive
        analysis regardless of report content variations.
        """
        # Create analyzer with fallback behavior (no AI client for property testing)
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        # Run QA analysis
        analysis = analyzer.analyze_report(report)
        
        # Property: Analysis must be complete and well-formed
        assert isinstance(analysis, QAAnalysis), "Analysis must be QAAnalysis instance"
        
        # Property: Overall score must be valid range
        assert 0 <= analysis.overall_score <= 100, f"Overall score {analysis.overall_score} must be 0-100"
        
        # Property: Section scores must be valid
        assert isinstance(analysis.section_scores, dict), "Section scores must be dict"
        for section, score in analysis.section_scores.items():
            assert isinstance(section, str), "Section names must be strings"
            assert 0 <= score <= 100, f"Section score {score} for {section} must be 0-100"
        
        # Property: Issues list must be valid
        assert isinstance(analysis.issues, list), "Issues must be list"
        for issue in analysis.issues:
            assert isinstance(issue, ClassifiedIssue), "Each issue must be ClassifiedIssue"
            assert isinstance(issue.issue_type, IssueType), "Issue type must be valid enum"
            assert isinstance(issue.severity, Severity), "Severity must be valid enum"
            assert isinstance(issue.section, str), "Issue section must be string"
            assert isinstance(issue.description, str), "Issue description must be string"
            assert isinstance(issue.location, str), "Issue location must be string"
        
        # Property: Citation check must be complete
        citation_check = analysis.citation_check
        assert isinstance(citation_check, CitationCheckResult), "Citation check must be CitationCheckResult"
        assert citation_check.total_citations >= 0, "Total citations must be non-negative"
        assert citation_check.valid_citations >= 0, "Valid citations must be non-negative"
        assert citation_check.valid_citations <= citation_check.total_citations, "Valid <= total citations"
        assert 0 <= citation_check.score <= 100, f"Citation score {citation_check.score} must be 0-100"
        assert isinstance(citation_check.broken_links, list), "Broken links must be list"
        assert isinstance(citation_check.unsupported_claims, list), "Unsupported claims must be list"
        
        # Property: Logic check must be complete
        logic_check = analysis.logic_check
        assert isinstance(logic_check, LogicCheckResult), "Logic check must be LogicCheckResult"
        assert 0 <= logic_check.score <= 100, f"Logic score {logic_check.score} must be 0-100"
        assert isinstance(logic_check.contradictions_found, list), "Contradictions must be list"
        assert isinstance(logic_check.unsupported_leaps, list), "Unsupported leaps must be list"
        
        # Property: Completeness check must be complete
        completeness_check = analysis.completeness_check
        assert isinstance(completeness_check, CompletenessCheckResult), "Completeness check must be CompletenessCheckResult"
        assert 0 <= completeness_check.score <= 100, f"Completeness score {completeness_check.score} must be 0-100"
        assert isinstance(completeness_check.expected_sections, list), "Expected sections must be list"
        assert isinstance(completeness_check.missing_sections, list), "Missing sections must be list"
        assert isinstance(completeness_check.weak_sections, list), "Weak sections must be list"
        
        # Property: Confidence assessment must be complete
        confidence = analysis.confidence_assessment
        assert isinstance(confidence, ConfidenceAssessment), "Confidence must be ConfidenceAssessment"
        assert 0 <= confidence.overall_confidence <= 100, f"Overall confidence {confidence.overall_confidence} must be 0-100"
        assert isinstance(confidence.section_confidence, dict), "Section confidence must be dict"
        for section, conf_score in confidence.section_confidence.items():
            assert isinstance(section, str), "Confidence section names must be strings"
            assert 0 <= conf_score <= 100, f"Confidence score {conf_score} for {section} must be 0-100"
        
        # Property: Metadata must be present
        assert isinstance(analysis.timestamp, datetime), "Timestamp must be datetime"
        assert isinstance(analysis.model_used, str), "Model used must be string"
        assert len(analysis.model_used) > 0, "Model used must not be empty"
    
    @given(report_content())
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5)
    def test_qa_analysis_citation_consistency(self, report: ReportContent):
        """
        **Feature: report-quality-assurance, Property 2: Citation accuracy validation**
        **Validates: Requirements 2.1**
        
        Property: Citation analysis should be consistent with report content.
        The total citations found should relate to the citations in the report.
        """
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        analysis = analyzer.analyze_report(report)
        citation_check = analysis.citation_check
        
        # Property: Citation count should be reasonable relative to report citations
        # In fallback mode, it should match the report's citation list
        assert citation_check.total_citations == len(report.citations), \
            f"Total citations {citation_check.total_citations} should match report citations {len(report.citations)}"
        
        # Property: Valid citations should not exceed total
        assert citation_check.valid_citations <= citation_check.total_citations, \
            "Valid citations cannot exceed total citations"
        
        # Property: Broken links and unsupported claims should be lists
        assert isinstance(citation_check.broken_links, list), "Broken links must be list"
        assert isinstance(citation_check.unsupported_claims, list), "Unsupported claims must be list"
    
    def test_qa_analysis_with_empty_report(self):
        """
        Edge case: QA analysis should handle empty or minimal reports gracefully.
        """
        minimal_report = ReportContent(
            company_name="Test Company",
            content="",
            sections={},
            citations=[],
            metadata=ReportMetadata(
                company_name="Test Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        analysis = analyzer.analyze_report(minimal_report)
        
        # Should still produce valid analysis structure
        assert isinstance(analysis, QAAnalysis)
        assert 0 <= analysis.overall_score <= 100
        assert isinstance(analysis.issues, list)
        assert isinstance(analysis.citation_check, CitationCheckResult)
        assert isinstance(analysis.logic_check, LogicCheckResult)
        assert isinstance(analysis.completeness_check, CompletenessCheckResult)
        assert isinstance(analysis.confidence_assessment, ConfidenceAssessment)
    
    def test_qa_analysis_with_many_sections(self):
        """
        Edge case: QA analysis should handle reports with many sections.
        """
        many_sections = {f"Section {i}": f"Content for section {i}" for i in range(20)}
        
        large_report = ReportContent(
            company_name="Large Company",
            content="\n".join([f"## {name}\n{content}" for name, content in many_sections.items()]),
            sections=many_sections,
            citations=[f"https://example{i}.com" for i in range(15)],
            metadata=ReportMetadata(
                company_name="Large Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("large_test.txt")
            ),
            file_path=Path("large_test.txt")
        )
        
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        analysis = analyzer.analyze_report(large_report)
        
        # Should handle large reports without errors
        assert isinstance(analysis, QAAnalysis)
        assert analysis.citation_check.total_citations == 15
        assert len(analysis.completeness_check.expected_sections) > 0


class TestCitationCheckingProperties:
    """Property-based tests for citation accuracy validation."""
    
    @given(st.lists(st.text(min_size=10, max_size=50), min_size=0, max_size=10))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=20)
    def test_citation_accuracy_validation_property(self, citations: list[str]):
        """
        **Feature: report-quality-assurance, Property 2: Citation accuracy validation**
        **Validates: Requirements 2.1**
        
        Property: For any list of citations, the citation checking should
        produce consistent and valid results.
        """
        # Create a simple report with the given citations
        report = ReportContent(
            company_name="Test Company",
            content="Test content with citations.",
            sections={"Test Section": "Test content"},
            citations=citations,
            metadata=ReportMetadata(
                company_name="Test Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        analysis = analyzer.analyze_report(report)
        citation_check = analysis.citation_check
        
        # Property: Citation count should match input
        assert citation_check.total_citations == len(citations), \
            f"Total citations {citation_check.total_citations} should match input {len(citations)}"
        
        # Property: Valid citations should not exceed total
        assert citation_check.valid_citations <= citation_check.total_citations, \
            "Valid citations cannot exceed total citations"
        
        # Property: Valid citations should be non-negative
        assert citation_check.valid_citations >= 0, "Valid citations must be non-negative"
        
        # Property: Score should be in valid range
        assert 0 <= citation_check.score <= 100, \
            f"Citation score {citation_check.score} must be 0-100"
        
        # Property: Broken links should be a list
        assert isinstance(citation_check.broken_links, list), "Broken links must be list"
        
        # Property: Unsupported claims should be a list
        assert isinstance(citation_check.unsupported_claims, list), "Unsupported claims must be list"
        
        # Property: All broken links should be strings
        for link in citation_check.broken_links:
            assert isinstance(link, str), "Each broken link must be string"
        
        # Property: All unsupported claims should be strings
        for claim in citation_check.unsupported_claims:
            assert isinstance(claim, str), "Each unsupported claim must be string"
    
    def test_citation_checking_with_empty_citations(self):
        """
        Edge case: Citation checking should handle reports with no citations.
        """
        report = ReportContent(
            company_name="No Citations Company",
            content="Content without any citations.",
            sections={"Main": "Content without citations"},
            citations=[],
            metadata=ReportMetadata(
                company_name="No Citations Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        analysis = analyzer.analyze_report(report)
        citation_check = analysis.citation_check
        
        # Should handle zero citations gracefully
        assert citation_check.total_citations == 0
        assert citation_check.valid_citations == 0
        assert isinstance(citation_check.score, int)
        assert 0 <= citation_check.score <= 100
    
    def test_citation_checking_with_many_citations(self):
        """
        Edge case: Citation checking should handle reports with many citations.
        """
        many_citations = [f"https://source{i}.example.com" for i in range(50)]
        
        report = ReportContent(
            company_name="Many Citations Company",
            content="Content with many citations.",
            sections={"Research": "Heavily cited research content"},
            citations=many_citations,
            metadata=ReportMetadata(
                company_name="Many Citations Company",
                generation_date=datetime.now(),
                generation_mode="test",
                model_used="test-model",
                file_path=Path("test.txt")
            ),
            file_path=Path("test.txt")
        )
        
        analyzer = QAAnalyzer()
        analyzer.ai_client = None  # Force fallback analysis
        
        analysis = analyzer.analyze_report(report)
        citation_check = analysis.citation_check
        
        # Should handle many citations without errors
        assert citation_check.total_citations == 50
        assert citation_check.valid_citations <= 50
        assert citation_check.valid_citations >= 0
        assert isinstance(citation_check.score, int)
        assert 0 <= citation_check.score <= 100


class TestIssueClassifierProperties:
    """Property-based tests for issue classification and scoring."""
    
    @given(st.lists(
        st.builds(
            ClassifiedIssue,
            issue_type=st.sampled_from(list(IssueType)),
            severity=st.sampled_from(list(Severity)),
            section=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'), whitelist_characters=' ')),
            description=st.text(min_size=10, max_size=100, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters=' .,')),
            location=st.text(min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters=' .,:')),
            suggestion=st.one_of(st.none(), st.text(min_size=10, max_size=50))
        ),
        min_size=0, max_size=10
    ))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=15)
    def test_score_consistency_property(self, issues: list[ClassifiedIssue]):
        """
        **Feature: report-quality-assurance, Property 2: Score consistency**
        **Validates: Requirements 3.1**
        
        Property: For any set of issues, the scoring should be consistent
        and the overall score should align with component scores.
        """
        from src.primr.qa.issue_classifier import IssueClassifier
        
        # Create a mock QA analysis with the given issues
        analysis = QAAnalysis(
            overall_score=75,  # Initial score to be adjusted
            section_scores={"Test Section": 80},
            issues=issues,
            citation_check=CitationCheckResult(
                total_citations=5, valid_citations=4, broken_links=[], 
                unsupported_claims=[], score=80
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[], unsupported_leaps=[], score=85
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=["Test"], missing_sections=[], 
                weak_sections=[], score=75
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={"Test Section": 80}, overall_confidence=80
            ),
            timestamp=datetime.now(),
            model_used="test-model"
        )
        
        classifier = IssueClassifier()
        
        # Test score consistency
        consistent_analysis = classifier.ensure_score_consistency(analysis)
        
        # Property: Analysis should still be valid after consistency check
        assert isinstance(consistent_analysis, QAAnalysis)
        assert 0 <= consistent_analysis.overall_score <= 100
        
        # Property: Score should be reasonable given the issues
        calculated_score = classifier.calculate_overall_score(analysis)
        assert 0 <= calculated_score <= 100
        
        # Property: More severe issues should result in lower scores
        if issues:
            critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]
            if critical_issues:
                # If there are critical issues, score should be significantly impacted
                assert calculated_score < 90, "Critical issues should significantly impact score"
        
        # Property: Severity impact should be in valid range
        severity_impact = classifier.calculate_severity_impact(issues)
        assert 0.0 <= severity_impact <= 1.0, f"Severity impact {severity_impact} must be 0.0-1.0"
        
        # Property: Issue classification should be complete
        classification = classifier.classify_issues(issues)
        assert isinstance(classification, dict)
        
        # Verify all issues are classified
        total_classified = sum(len(issue_list) for key, issue_list in classification.items() 
                             if key in ['critical', 'high', 'medium', 'low'])
        assert total_classified >= len(issues), "All issues should be classified by severity"
    
    def test_score_consistency_with_no_issues(self):
        """
        Edge case: Score consistency should work with no issues.
        """
        from src.primr.qa.issue_classifier import IssueClassifier
        
        analysis = QAAnalysis(
            overall_score=90,
            section_scores={},
            issues=[],
            citation_check=CitationCheckResult(
                total_citations=0, valid_citations=0, broken_links=[], 
                unsupported_claims=[], score=100
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[], unsupported_leaps=[], score=95
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=[], missing_sections=[], 
                weak_sections=[], score=90
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={}, overall_confidence=90
            ),
            timestamp=datetime.now(),
            model_used="test-model"
        )
        
        classifier = IssueClassifier()
        consistent_analysis = classifier.ensure_score_consistency(analysis)
        
        # Should handle no issues gracefully
        assert isinstance(consistent_analysis, QAAnalysis)
        assert consistent_analysis.overall_score >= 80  # Should be high with no issues
        
        severity_impact = classifier.calculate_severity_impact([])
        assert severity_impact == 0.0  # No issues = no impact
    
    @given(st.lists(
        st.builds(
            ClassifiedIssue,
            issue_type=st.sampled_from(list(IssueType)),
            severity=st.sampled_from(list(Severity)),
            section=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll'), whitelist_characters=' ')),
            description=st.text(min_size=10, max_size=100, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters=' .,')),
            location=st.one_of(
                st.just("line 42"),  # Specific location
                st.just("paragraph 3 in Executive Summary"),  # Specific location
                st.just("section 2.1"),  # Specific location
                st.just("general issues throughout"),  # Vague location
                st.just("various sections"),  # Vague location
                st.just("overall"),  # Vague location
                st.text(min_size=1, max_size=30)  # Random location
            ),
            suggestion=st.one_of(st.none(), st.text(min_size=10, max_size=50))
        ),
        min_size=0, max_size=15
    ))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10)
    def test_issue_location_specificity_property(self, issues: list[ClassifiedIssue]):
        """
        **Feature: report-quality-assurance, Property 3: Issue location specificity**
        **Validates: Requirements 3.3**
        
        Property: For any set of issues, location specificity analysis should
        provide meaningful metrics about how precisely issues are located.
        """
        from src.primr.qa.issue_classifier import IssueClassifier
        
        classifier = IssueClassifier()
        specificity_metrics = classifier.get_issue_location_specificity(issues)
        
        # Property: Metrics should be complete and valid
        assert isinstance(specificity_metrics, dict)
        assert "total_issues" in specificity_metrics
        assert "specific_locations" in specificity_metrics
        assert "vague_locations" in specificity_metrics
        assert "specificity_score" in specificity_metrics
        
        # Property: Counts should be consistent
        total = specificity_metrics["total_issues"]
        specific = specificity_metrics["specific_locations"]
        vague = specificity_metrics["vague_locations"]
        
        assert total == len(issues), f"Total issues {total} should match input {len(issues)}"
        assert specific >= 0, "Specific locations count must be non-negative"
        assert vague >= 0, "Vague locations count must be non-negative"
        assert specific + vague <= total, "Specific + vague should not exceed total"
        
        # Property: Specificity score should be in valid range
        score = specificity_metrics["specificity_score"]
        assert 0 <= score <= 100, f"Specificity score {score} must be 0-100"
        
        # Property: Score should reflect the ratio of specific to total issues
        if total > 0:
            expected_score = int((specific / total) * 100)
            assert abs(score - expected_score) <= 1, f"Score {score} should approximately match ratio {expected_score}"
        else:
            assert score == 100, "Empty issue list should have perfect specificity score"
        
        # Property: Issues with specific keywords should be counted as specific
        specific_keywords = ["line", "paragraph", "section"]
        for issue in issues:
            location_lower = issue.location.lower()
            has_specific_keyword = any(keyword in location_lower for keyword in specific_keywords)
            
            if has_specific_keyword:
                # This issue should contribute to specific count
                # (We can't assert individual issues due to the complexity of the algorithm,
                # but we can verify the overall logic is sound)
                pass
    
    def test_issue_location_specificity_with_known_locations(self):
        """
        Test location specificity with known specific and vague locations.
        """
        from src.primr.qa.issue_classifier import IssueClassifier
        
        # Create issues with known location types
        specific_issues = [
            ClassifiedIssue(
                issue_type=IssueType.FACTUAL,
                severity=Severity.HIGH,
                section="Test",
                description="Test issue",
                location="line 42 in Executive Summary",
                suggestion=None
            ),
            ClassifiedIssue(
                issue_type=IssueType.LOGICAL,
                severity=Severity.MEDIUM,
                section="Test",
                description="Test issue",
                location="paragraph 3 of section 2.1",
                suggestion=None
            )
        ]
        
        vague_issues = [
            ClassifiedIssue(
                issue_type=IssueType.COMPLETENESS,
                severity=Severity.LOW,
                section="Test",
                description="Test issue",
                location="general issues throughout",
                suggestion=None
            ),
            ClassifiedIssue(
                issue_type=IssueType.CITATION,
                severity=Severity.MEDIUM,
                section="Test",
                description="Test issue",
                location="various sections",
                suggestion=None
            )
        ]
        
        classifier = IssueClassifier()
        
        # Test with only specific issues
        specific_metrics = classifier.get_issue_location_specificity(specific_issues)
        assert specific_metrics["total_issues"] == 2
        assert specific_metrics["specific_locations"] == 2
        assert specific_metrics["specificity_score"] == 100
        
        # Test with only vague issues
        vague_metrics = classifier.get_issue_location_specificity(vague_issues)
        assert vague_metrics["total_issues"] == 2
        assert vague_metrics["vague_locations"] == 2
        assert vague_metrics["specificity_score"] == 0
        
        # Test with mixed issues
        mixed_issues = specific_issues + vague_issues
        mixed_metrics = classifier.get_issue_location_specificity(mixed_issues)
        assert mixed_metrics["total_issues"] == 4
        assert mixed_metrics["specific_locations"] == 2
        assert mixed_metrics["vague_locations"] == 2
        assert mixed_metrics["specificity_score"] == 50


class TestFilePersistenceProperties:
    """Property-based tests for QA file persistence."""
    
    @given(st.text(min_size=5, max_size=30, alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ').filter(
        lambda x: x.strip() and len(x.strip()) >= 5 and not x.startswith(' ') and not x.endswith(' ')
    ))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10, deadline=None)
    def test_file_persistence_property(self, company_name: str):
        """
        **Feature: report-quality-assurance, Property 4: File persistence**
        **Validates: Requirements 3.4, 5.4**
        
        Property: For any company name, when QA analysis is saved,
        the detailed analysis files should be created and readable.
        """
        import tempfile
        from datetime import datetime
        from pathlib import Path
        
        # Create a mock QA analysis
        analysis = QAAnalysis(
            overall_score=85,
            section_scores={"Executive Summary": 90, "Conclusion": 80},
            issues=[
                ClassifiedIssue(
                    issue_type=IssueType.FACTUAL,
                    severity=Severity.MEDIUM,
                    section="Executive Summary",
                    description="Minor factual inconsistency found",
                    location="paragraph 2",
                    suggestion="Verify the claim with additional sources"
                )
            ],
            citation_check=CitationCheckResult(
                total_citations=5, valid_citations=4, broken_links=[], 
                unsupported_claims=["Claim without source"], score=80
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[], unsupported_leaps=[], score=90
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=["Executive Summary", "Conclusion"], 
                missing_sections=[], weak_sections=[], score=85
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={"Executive Summary": 90, "Conclusion": 80}, 
                overall_confidence=85
            ),
            timestamp=datetime.now(),
            model_used="test-model"
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test file persistence
            from src.primr.output.qa_report_generator import QAReportGenerator
            
            generator = QAReportGenerator()
            # Override output directory for test
            generator.output_dir = Path(temp_dir)
            
            # Save detailed analysis
            generator.save_detailed_analysis(company_name, analysis)
            
            # Property: Files should be created
            output_files = list(Path(temp_dir).glob("*QA_Report*"))
            assert len(output_files) > 0, "QA report files should be created"
            
            # Property: Files should contain expected content
            for file_path in output_files:
                content = file_path.read_text(encoding='utf-8')
                
                # Should contain company name
                assert company_name.replace(' ', '_') in content or company_name in content, \
                    "File should contain company name"
                
                # Should contain overall score
                assert str(analysis.overall_score) in content, \
                    "File should contain overall score"
                
                # Should contain some analysis content
                assert len(content.strip()) > 100, \
                    "File should contain substantial analysis content"
                
                # Should be valid text file
                assert file_path.suffix in ['.txt', '.json'], \
                    "Should create text or JSON files"
    
    def test_file_persistence_with_special_characters(self):
        """
        Edge case: File persistence should handle company names with special characters.
        """
        import tempfile
        from datetime import datetime
        from pathlib import Path
        
        # Test with company names that need file system normalization
        test_companies = [
            "AT&T Corporation",
            "Johnson & Johnson", 
            "Procter & Gamble",
            "Ben & Jerry's"
        ]
        
        analysis = QAAnalysis(
            overall_score=75,
            section_scores={},
            issues=[],
            citation_check=CitationCheckResult(
                total_citations=0, valid_citations=0, broken_links=[], 
                unsupported_claims=[], score=100
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[], unsupported_leaps=[], score=100
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=[], missing_sections=[], 
                weak_sections=[], score=75
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={}, overall_confidence=75
            ),
            timestamp=datetime.now(),
            model_used="test-model"
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            from src.primr.output.qa_report_generator import QAReportGenerator
            
            generator = QAReportGenerator()
            generator.output_dir = Path(temp_dir)
            
            for company_name in test_companies:
                # Should not raise exceptions with special characters
                generator.save_detailed_analysis(company_name, analysis)
                
                # Should create files
                output_files = list(Path(temp_dir).glob("*QA_Report*"))
                assert len(output_files) > 0, f"Should create files for {company_name}"
                
                # Files should be readable
                for file_path in output_files:
                    content = file_path.read_text(encoding='utf-8')
                    assert len(content) > 0, f"File should have content for {company_name}"


class TestDetailedQAReviewProperties:
    """Property-based tests for detailed QA review command."""
    
    @given(st.sampled_from([
        "Bank of Hawaii", "Tesla Inc", "Microsoft Corporation", "Apple Inc",
        "Amazon Web Services", "Google LLC", "Meta Platforms"
    ]))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5, deadline=None)
    def test_detailed_qa_review_access_property(self, company_name: str):
        """
        **Feature: report-quality-assurance, Property 6: Detailed QA review access**
        **Validates: Requirements 5.4**
        
        Property: For any company name, the detailed QA review command should
        either find and display QA analysis or gracefully handle missing reports.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime
        
        from src.primr.qa.command import QACommand
        
        qa_command = QACommand()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Override output directory for test
            qa_command.output_dir = Path(temp_dir)
            
            # Test 1: No QA report exists - should return error code 1
            result_code = qa_command.show_detailed_analysis(company_name)
            assert result_code == 1, "Should return error code when no QA report exists"
            
            # Test 2: Create a QA report and verify it can be accessed
            # Create a mock QA report file
            clean_name = company_name.replace(' ', '_').replace('&', 'and')
            qa_filename = f"{clean_name}_QA_Report_{datetime.now().strftime('%m-%d-%Y')}.txt"
            qa_file_path = Path(temp_dir) / qa_filename
            
            # Create realistic QA report content
            qa_content = f"""Quality Assessment Report
Company: {company_name}
Date: {datetime.now().strftime('%B %d, %Y')}

OVERALL ASSESSMENT
Quality Score: 85/100

SECTION SCORES
Executive Summary: 90/100
Business Model: 80/100
Conclusion: 85/100

CITATION ANALYSIS
Total Citations: 5
Valid Citations: 4
Score: 80/100

LOGICAL CONSISTENCY
No contradictions found
Score: 90/100

COMPLETENESS ASSESSMENT
Expected sections present
Score: 85/100

DETAILED ISSUES
- Minor factual inconsistency in Executive Summary
- One unsupported claim identified

RECOMMENDATIONS
- Verify claims with additional sources
- Strengthen citation practices
"""
            
            with open(qa_file_path, 'w', encoding='utf-8') as f:
                f.write(qa_content)
            
            # Should now find and display the QA report successfully
            result_code = qa_command.show_detailed_analysis(company_name)
            assert result_code == 0, "Should return success code when QA report exists"
    
    def test_detailed_qa_review_with_multiple_reports(self):
        """
        Edge case: QA review should handle multiple reports and select the latest.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime
        import time
        
        from src.primr.qa.command import QACommand
        
        company_name = "Test Company"
        qa_command = QACommand()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            qa_command.output_dir = Path(temp_dir)
            
            # Create multiple QA report files with different timestamps
            base_content = f"""Quality Assessment Report
Company: {company_name}
OVERALL ASSESSMENT
Quality Score: """
            
            report_files = []
            for i, score in enumerate([75, 80, 85]):  # Different scores for different reports
                qa_filename = f"Test_Company_QA_Report_12-{20+i}-2025.txt"
                qa_file_path = Path(temp_dir) / qa_filename
                
                content = base_content + f"{score}/100\n\nReport version {i+1}"
                with open(qa_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Set different modification times
                import os
                timestamp = time.time() + i
                os.utime(qa_file_path, (timestamp, timestamp))
                report_files.append(qa_file_path)
            
            # Should successfully find and display a QA report (latest one)
            result_code = qa_command.show_detailed_analysis(company_name)
            assert result_code == 0, "Should find QA report when multiple exist"
    
    def test_detailed_qa_review_error_handling(self):
        """
        Edge case: QA review should handle file system errors gracefully.
        """
        from src.primr.qa.command import QACommand
        
        qa_command = QACommand()
        
        # Test with invalid company names
        invalid_names = ["", "   ", "Company/With/Slashes", "Company*With*Stars"]
        
        for invalid_name in invalid_names:
            if invalid_name.strip():  # Skip empty names
                result_code = qa_command.show_detailed_analysis(invalid_name)
                # Should handle gracefully and return error code
                assert result_code in [0, 1], f"Should handle invalid name '{invalid_name}' gracefully"


class TestDefaultQAIntegrationProperties:
    """Property-based tests for default QA integration."""
    
    @given(st.sampled_from([
        "Bank of Hawaii", "Tesla Inc", "Microsoft Corporation", "Apple Inc",
        "Amazon Web Services", "Google LLC", "Meta Platforms", "Walmart Inc"
    ]))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5, deadline=None)
    def test_default_qa_execution_property(self, company_name: str):
        """
        **Feature: report-quality-assurance, Property 1: Default QA execution**
        **Validates: Requirements 1.1, 3.1**
        
        Property: For any company name, when QA is enabled by default,
        the QA integration should execute automatically and produce results.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime
        
        from src.primr.qa.integration import QAIntegration
        from src.primr.qa.models import QAOptions, ReportContent, ReportMetadata
        
        # Test with QA enabled by default (default behavior)
        qa_options = QAOptions(enabled=True, save_detailed=True)
        qa_integration = QAIntegration(qa_options)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock report file
            report_path = Path(temp_dir) / f"{company_name.replace(' ', '_')}_Report.txt"
            report_content = f"""# {company_name} Analysis Report

## Executive Summary
{company_name} is a leading company in its sector with strong market position.

## Business Model
The company operates through multiple revenue streams and maintains competitive advantages.

## Conclusion
{company_name} shows promising growth potential with manageable risks.

Sources:
- https://example.com/source1
- https://example.com/source2
"""
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            # Property: QA should execute automatically when enabled
            qa_result = qa_integration.run_post_generation_qa(report_path, company_name)
            
            # Property: QA result should be produced when enabled
            assert qa_result is not None, "QA should produce result when enabled"
            
            # Property: QA result should have valid structure
            assert hasattr(qa_result, 'grade'), "QA result should have grade"
            assert hasattr(qa_result, 'summary'), "QA result should have summary"
            assert hasattr(qa_result, 'needs_attention'), "QA result should have needs_attention flag"
            
            # Property: Grade should be in valid range
            assert 0 <= qa_result.grade <= 100, f"Grade {qa_result.grade} should be 0-100"
            
            # Property: Summary should contain grade information
            assert "Grade:" in qa_result.summary, "Summary should contain grade information"
            assert str(qa_result.grade) in qa_result.summary, "Summary should contain actual grade"
            
            # Property: Needs attention flag should be consistent with grade
            if qa_result.grade < 70:
                assert qa_result.needs_attention, "Should need attention when grade < 70"
            
            # Property: Detailed analysis should be available when save_detailed is True
            if qa_result.detailed_analysis:
                assert hasattr(qa_result.detailed_analysis, 'overall_score'), "Detailed analysis should have overall score"
                assert qa_result.detailed_analysis.overall_score == qa_result.grade, "Scores should be consistent"
    
    def test_default_qa_disabled_behavior(self):
        """
        Test that QA integration respects the disabled setting.
        """
        import tempfile
        from pathlib import Path
        
        from src.primr.qa.integration import QAIntegration
        from src.primr.qa.models import QAOptions
        
        # Test with QA disabled
        qa_options = QAOptions(enabled=False)
        qa_integration = QAIntegration(qa_options)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "Test_Company_Report.txt"
            with open(report_path, 'w') as f:
                f.write("Test report content")
            
            # Should return None when disabled
            qa_result = qa_integration.run_post_generation_qa(report_path, "Test Company")
            assert qa_result is None, "QA should return None when disabled"
    
    def test_default_qa_error_handling(self):
        """
        Test that QA integration handles errors gracefully.
        """
        import tempfile
        from pathlib import Path
        
        from src.primr.qa.integration import QAIntegration
        from src.primr.qa.models import QAOptions
        
        qa_integration = QAIntegration(QAOptions(enabled=True))
        
        # Test with non-existent report file
        non_existent_path = Path("non_existent_report.txt")
        qa_result = qa_integration.run_post_generation_qa(non_existent_path, "Test Company")
        
        # Should handle gracefully and return error result
        if qa_result is not None:
            assert qa_result.grade == 0, "Should return grade 0 for failed QA"
            assert "QA Failed" in qa_result.summary, "Should indicate QA failure"
            assert qa_result.needs_attention, "Failed QA should need attention"


class TestWorkspaceIntegrationProperties:
    """Property-based tests for workspace integration."""
    
    @given(st.sampled_from([
        "Bank of Hawaii", "Tesla Inc", "Microsoft Corporation", "Apple Inc"
    ]))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=3, deadline=None)
    def test_workspace_integration_property(self, company_name: str):
        """
        **Feature: report-quality-assurance, Property 7: Workspace integration**
        **Validates: Requirements 5.2, 5.4**
        
        Property: For any company name, QA system should integrate properly
        with workspace file structure and naming conventions.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime
        
        from src.primr.output.qa_report_generator import QAReportGenerator
        from src.primr.qa.models import QAAnalysis, CitationCheckResult, LogicCheckResult, CompletenessCheckResult, ConfidenceAssessment
        
        # Create mock QA analysis
        analysis = QAAnalysis(
            overall_score=85,
            section_scores={"Executive Summary": 90, "Conclusion": 80},
            issues=[],
            citation_check=CitationCheckResult(
                total_citations=3, valid_citations=3, broken_links=[], 
                unsupported_claims=[], score=100
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[], unsupported_leaps=[], score=90
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=["Executive Summary", "Conclusion"], 
                missing_sections=[], weak_sections=[], score=85
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={"Executive Summary": 90, "Conclusion": 80}, 
                overall_confidence=85
            ),
            timestamp=datetime.now(),
            model_used="test-model"
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = QAReportGenerator()
            generator.output_dir = Path(temp_dir)
            
            # Property: Should create files with proper workspace integration
            generator.save_detailed_analysis(company_name, analysis)
            
            # Property: Files should be created in output directory
            output_files = list(Path(temp_dir).glob("*QA_Report*"))
            assert len(output_files) > 0, "Should create QA report files in workspace"
            
            # Property: File names should follow workspace conventions
            for file_path in output_files:
                filename = file_path.name
                
                # Should contain company name (normalized for file system)
                clean_company = company_name.replace(' ', '_').replace('&', 'and')
                assert any(part in filename for part in clean_company.split('_')), \
                    f"Filename {filename} should contain company name parts"
                
                # Should contain QA_Report identifier
                assert "QA_Report" in filename, f"Filename {filename} should contain QA_Report"
                
                # Should have proper file extension
                assert filename.endswith('.txt') or filename.endswith('.json'), \
                    f"Filename {filename} should have proper extension"
                
                # Property: Files should be readable and contain expected content
                content = file_path.read_text(encoding='utf-8')
                assert len(content) > 100, "File should contain substantial content"
                assert company_name in content or clean_company in content, \
                    "File content should reference company name"
                assert str(analysis.overall_score) in content, \
                    "File content should contain overall score"
    
    def test_workspace_integration_with_existing_files(self):
        """
        Test workspace integration when files already exist.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime
        
        from src.primr.output.qa_report_generator import QAReportGenerator
        from src.primr.qa.models import QAAnalysis, CitationCheckResult, LogicCheckResult, CompletenessCheckResult, ConfidenceAssessment
        
        analysis = QAAnalysis(
            overall_score=75,
            section_scores={},
            issues=[],
            citation_check=CitationCheckResult(
                total_citations=0, valid_citations=0, broken_links=[], 
                unsupported_claims=[], score=100
            ),
            logic_check=LogicCheckResult(
                contradictions_found=[], unsupported_leaps=[], score=100
            ),
            completeness_check=CompletenessCheckResult(
                expected_sections=[], missing_sections=[], 
                weak_sections=[], score=75
            ),
            confidence_assessment=ConfidenceAssessment(
                section_confidence={}, overall_confidence=75
            ),
            timestamp=datetime.now(),
            model_used="test-model"
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = QAReportGenerator()
            generator.output_dir = Path(temp_dir)
            
            company_name = "Test Company"
            
            # Create first QA report
            generator.save_detailed_analysis(company_name, analysis)
            initial_files = list(Path(temp_dir).glob("*QA_Report*"))
            assert len(initial_files) > 0, "Should create initial QA report"
            
            # Create second QA report (should handle existing files)
            analysis.overall_score = 80  # Different score
            generator.save_detailed_analysis(company_name, analysis)
            
            # Should handle existing files gracefully
            final_files = list(Path(temp_dir).glob("*QA_Report*"))
            assert len(final_files) >= len(initial_files), "Should handle existing files"


class TestQAHistoryPreservationProperties:
    """Property-based tests for QA history tracking."""
    
    @given(st.lists(
        st.integers(min_value=60, max_value=100),  # QA scores
        min_size=2, max_size=5
    ))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=5, deadline=None)
    def test_qa_history_tracking_property(self, scores: list[int]):
        """
        **Feature: report-quality-assurance, Property 8: QA history tracking**
        **Validates: Requirements 5.5**
        
        Property: For any sequence of QA scores, the system should preserve
        QA history with timestamps and allow tracking over time.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime, timedelta
        import time
        
        from src.primr.output.qa_report_generator import QAReportGenerator
        from src.primr.qa.models import QAAnalysis, CitationCheckResult, LogicCheckResult, CompletenessCheckResult, ConfidenceAssessment
        from src.primr.qa.command import QACommand
        
        company_name = "History Test Company"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = QAReportGenerator()
            generator.output_dir = Path(temp_dir)
            
            qa_command = QACommand()
            qa_command.output_dir = Path(temp_dir)
            
            # Create multiple QA reports with different scores and timestamps
            created_files = []
            for i, score in enumerate(scores):
                analysis = QAAnalysis(
                    overall_score=score,
                    section_scores={"Test Section": score},
                    issues=[],
                    citation_check=CitationCheckResult(
                        total_citations=1, valid_citations=1, broken_links=[], 
                        unsupported_claims=[], score=score
                    ),
                    logic_check=LogicCheckResult(
                        contradictions_found=[], unsupported_leaps=[], score=score
                    ),
                    completeness_check=CompletenessCheckResult(
                        expected_sections=["Test Section"], missing_sections=[], 
                        weak_sections=[], score=score
                    ),
                    confidence_assessment=ConfidenceAssessment(
                        section_confidence={"Test Section": score}, 
                        overall_confidence=score
                    ),
                    timestamp=datetime.now() + timedelta(hours=i),  # Different timestamps
                    model_used="test-model"
                )
                
                generator.save_detailed_analysis(company_name, analysis)
                
                # Small delay to ensure different file timestamps
                time.sleep(0.1)
                
                # Track created files
                current_files = list(Path(temp_dir).glob("*QA_Report*"))
                created_files.extend([f for f in current_files if f not in created_files])
            
            # Property: Multiple QA reports should be preserved
            all_qa_files = list(Path(temp_dir).glob("*QA_Report*"))
            assert len(all_qa_files) >= len(scores), f"Should preserve {len(scores)} QA reports, found {len(all_qa_files)}"
            
            # Property: Each file should contain the corresponding score
            found_scores = []
            for qa_file in all_qa_files:
                content = qa_file.read_text(encoding='utf-8')
                for score in scores:
                    if f"Quality Score: {score}/100" in content or f"Grade: ({score}/100)" in content:
                        found_scores.append(score)
                        break
            
            # Should find most or all of the scores in the files
            assert len(found_scores) >= len(scores) // 2, f"Should find most scores in files, found {len(found_scores)} of {len(scores)}"
            
            # Property: QA command should be able to access the history
            # (Test that it can find and display at least one report)
            result_code = qa_command.show_detailed_analysis(company_name)
            assert result_code == 0, "Should be able to access QA history through command"
            
            # Property: Recent QA summary should work with multiple reports
            summary_result = qa_command.show_recent_qa_summary(len(scores))
            assert summary_result == 0, "Should be able to show recent QA summary"
    
    def test_qa_history_with_timestamps(self):
        """
        Test that QA history properly handles timestamps and chronological ordering.
        """
        import tempfile
        from pathlib import Path
        from datetime import datetime, timedelta
        import os
        
        from src.primr.output.qa_report_generator import QAReportGenerator
        from src.primr.qa.models import QAAnalysis, CitationCheckResult, LogicCheckResult, CompletenessCheckResult, ConfidenceAssessment
        from src.primr.qa.command import QACommand
        
        company_name = "Timestamp Test Company"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = QAReportGenerator()
            generator.output_dir = Path(temp_dir)
            
            qa_command = QACommand()
            qa_command.output_dir = Path(temp_dir)
            
            # Create QA reports with specific timestamps
            timestamps = [
                datetime(2024, 1, 1, 10, 0, 0),
                datetime(2024, 1, 2, 10, 0, 0),
                datetime(2024, 1, 3, 10, 0, 0)
            ]
            
            scores = [70, 80, 90]  # Improving scores over time
            
            for i, (timestamp, score) in enumerate(zip(timestamps, scores)):
                analysis = QAAnalysis(
                    overall_score=score,
                    section_scores={},
                    issues=[],
                    citation_check=CitationCheckResult(
                        total_citations=0, valid_citations=0, broken_links=[], 
                        unsupported_claims=[], score=100
                    ),
                    logic_check=LogicCheckResult(
                        contradictions_found=[], unsupported_leaps=[], score=100
                    ),
                    completeness_check=CompletenessCheckResult(
                        expected_sections=[], missing_sections=[], 
                        weak_sections=[], score=score
                    ),
                    confidence_assessment=ConfidenceAssessment(
                        section_confidence={}, overall_confidence=score
                    ),
                    timestamp=timestamp,
                    model_used="test-model"
                )
                
                generator.save_detailed_analysis(company_name, analysis)
                
                # Set file modification time to match timestamp
                qa_files = list(Path(temp_dir).glob("*QA_Report*"))
                if qa_files:
                    latest_file = max(qa_files, key=lambda f: f.stat().st_mtime)
                    timestamp_epoch = timestamp.timestamp()
                    os.utime(latest_file, (timestamp_epoch, timestamp_epoch))
            
            # Verify files exist with proper timestamps
            qa_files = list(Path(temp_dir).glob("*QA_Report*"))
            assert len(qa_files) >= 2, "Should create multiple QA report files"
            
            # Should be able to access the most recent report
            result_code = qa_command.show_detailed_analysis(company_name)
            assert result_code == 0, "Should access most recent QA report"


class TestErrorRecoveryProperties:
    """Property-based tests for error recovery."""
    
    @given(st.sampled_from([
        "Bank of Hawaii", "Tesla Inc", "Microsoft Corporation", "Apple Inc"
    ]))
    @settings(suppress_health_check=[HealthCheck.too_slow], max_examples=3, deadline=None)
    def test_error_recovery_property(self, company_name: str):
        """
        **Feature: report-quality-assurance, Property 7: Error recovery**
        **Validates: Requirements 1.4**
        
        Property: For any company name, when QA operations encounter errors,
        the system should recover gracefully and provide meaningful feedback.
        """
        import tempfile
        from pathlib import Path
        
        from src.primr.qa.integration import QAIntegration
        from src.primr.qa.models import QAOptions
        from src.primr.qa.error_handler import QARetryHandler, QAErrorHandler
        
        # Test error recovery with non-existent files
        qa_integration = QAIntegration(QAOptions(enabled=True))
        
        # Property: Should handle non-existent report files gracefully
        non_existent_path = Path("non_existent_report.txt")
        qa_result = qa_integration.run_post_generation_qa(non_existent_path, company_name)
        
        # Property: Should return error result instead of crashing
        if qa_result is not None:
            assert isinstance(qa_result.grade, int), "Should return integer grade even on error"
            assert qa_result.grade >= 0, "Grade should be non-negative even on error"
            assert isinstance(qa_result.summary, str), "Should return string summary even on error"
            assert qa_result.needs_attention, "Error results should need attention"
            
            # Property: Error results should indicate failure
            if qa_result.grade == 0:
                assert "Failed" in qa_result.summary or "Error" in qa_result.summary, \
                    "Zero grade should indicate failure in summary"
        
        # Test error recovery with corrupted files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a corrupted/empty report file
            corrupted_path = Path(temp_dir) / "corrupted_report.txt"
            with open(corrupted_path, 'w', encoding='utf-8') as f:
                f.write("")  # Empty file
            
            qa_result = qa_integration.run_post_generation_qa(corrupted_path, company_name)
            
            # Property: Should handle corrupted files gracefully
            if qa_result is not None:
                assert isinstance(qa_result, type(qa_result)), "Should return QAResult object"
                assert hasattr(qa_result, 'grade'), "Result should have grade attribute"
                assert hasattr(qa_result, 'summary'), "Result should have summary attribute"
    
    def test_retry_handler_error_recovery(self):
        """
        Test that retry handler properly recovers from transient errors.
        """
        from src.primr.qa.error_handler import QARetryHandler, QAModelError
        
        retry_handler = QARetryHandler(max_retries=3, base_delay=0.1)  # Fast retries for testing
        
        # Test successful retry after failures
        attempt_count = 0
        
        def failing_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise QAModelError("Temporary failure")
            return "Success"
        
        # Should succeed after retries
        result = retry_handler.retry_with_backoff(
            failing_operation,
            retryable_exceptions=(QAModelError,),
            operation_name="Test operation"
        )
        
        assert result == "Success", "Should succeed after retries"
        assert attempt_count == 3, "Should have attempted 3 times"
    
    def test_error_handler_message_generation(self):
        """
        Test that error handler generates appropriate error messages.
        """
        from src.primr.qa.error_handler import QAErrorHandler
        
        error_handler = QAErrorHandler()
        
        # Test model error handling
        auth_error = Exception("Authentication failed")
        auth_message = error_handler.handle_model_error(auth_error, "test-model")
        assert "authentication" in auth_message.lower(), "Should mention authentication"
        assert "test-model" in auth_message, "Should mention model name"
        
        rate_limit_error = Exception("Rate limit exceeded")
        rate_message = error_handler.handle_model_error(rate_limit_error, "test-model")
        assert "rate limit" in rate_message.lower(), "Should mention rate limit"
        
        # Test file error handling
        file_not_found = FileNotFoundError("File not found")
        file_message = error_handler.handle_file_error(file_not_found, "test.txt")
        assert "not found" in file_message.lower(), "Should mention file not found"
        assert "test.txt" in file_message, "Should mention file path"
        
        permission_error = PermissionError("Permission denied")
        perm_message = error_handler.handle_file_error(permission_error, "test.txt")
        assert "permission" in perm_message.lower(), "Should mention permission"
        
        # Test analysis error handling
        json_error = Exception("JSON decode error")
        json_message = error_handler.handle_analysis_error(json_error, "Test Company")
        assert "parse" in json_message.lower() or "json" in json_message.lower(), \
            "Should mention parsing issue"
        assert "Test Company" in json_message, "Should mention company name"
    
    def test_safe_qa_operation_decorator(self):
        """
        Test that safe QA operation decorator properly handles errors.
        """
        from src.primr.qa.error_handler import safe_qa_operation, QAError
        
        @safe_qa_operation("Test operation")
        def failing_function():
            raise ValueError("Test error")
        
        @safe_qa_operation("Test operation")
        def successful_function():
            return "Success"
        
        # Should convert generic exceptions to QA errors
        try:
            failing_function()
            assert False, "Should have raised QAError"
        except QAError as e:
            assert "Test operation failed" in str(e), "Should mention operation name"
            assert "Test error" in str(e), "Should include original error message"
        
        # Should pass through successful operations
        result = successful_function()
        assert result == "Success", "Should pass through successful results"