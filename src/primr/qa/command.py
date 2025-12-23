"""
QA command for detailed analysis review.
"""

import logging
from pathlib import Path
from typing import Optional

from ..utils.console import console
from .report_loader import ReportLoader

logger = logging.getLogger(__name__)


class QACommand:
    """Handles QA command-line operations."""
    
    def __init__(self):
        """Initialize QA command handler."""
        self.report_loader = ReportLoader()
        self.output_dir = Path("output")
    
    def show_detailed_analysis(self, company_name: str) -> int:
        """
        Show detailed QA analysis for a company.
        
        Args:
            company_name: Name of company to show QA analysis for
            
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            console.banner(f"QA Analysis: {company_name}")
            console.blank()
            
            # Find QA report file
            qa_report_path = self._find_qa_report(company_name)
            if not qa_report_path:
                console.error(f"No QA analysis found for {company_name}")
                console.info("QA analysis is generated automatically when reports are created.")
                console.info("To generate a new report with QA: primr \"Company Name\" https://company.com")
                return 1
            
            # Read and display QA report
            console.info(f"Reading QA analysis from: {qa_report_path.name}")
            console.blank()
            
            qa_content = qa_report_path.read_text(encoding='utf-8')
            
            # Display the content with some formatting
            lines = qa_content.split('\n')
            for line in lines:
                if line.startswith('='):
                    console.info(line)
                elif line.startswith('-'):
                    console.info(line)
                elif line.startswith('Quality Assessment Report'):
                    console.step(line)
                elif line.startswith('OVERALL ASSESSMENT'):
                    console.step(line)
                elif line.startswith('SECTION SCORES'):
                    console.step(line)
                elif line.startswith('CITATION ANALYSIS'):
                    console.step(line)
                elif line.startswith('LOGICAL CONSISTENCY'):
                    console.step(line)
                elif line.startswith('COMPLETENESS ASSESSMENT'):
                    console.step(line)
                elif line.startswith('DETAILED ISSUES'):
                    console.step(line)
                elif line.startswith('RECOMMENDATIONS'):
                    console.step(line)
                elif line.strip():
                    print(line)
                else:
                    print()
            
            console.blank()
            console.success_box("QA Analysis Complete", f"Report: {qa_report_path}")
            return 0
            
        except Exception as e:
            logger.error(f"Failed to show QA analysis for {company_name}: {e}")
            console.error(f"Failed to display QA analysis: {e}")
            return 1
    
    def show_recent_qa_summary(self, count: int = 5) -> int:
        """
        Show QA summary for the N most recent reports.
        
        Args:
            count: Number of recent reports to show QA for
            
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            console.banner(f"QA Summary: {count} Most Recent Reports")
            console.blank()
            
            # Get recent reports with QA data
            recent_reports = self._get_recent_reports_with_qa(count)
            
            if not recent_reports:
                console.error("No reports with QA analysis found")
                console.info("QA analysis is generated automatically when reports are created.")
                return 1
            
            # Display summary table
            console.info(f"Found {len(recent_reports)} report(s) with QA analysis:")
            console.blank()
            
            # Table header
            print(f"{'#':<3} {'Company':<30} {'Date':<12} {'Grade':<8} {'Status':<12}")
            print("-" * 70)
            
            for i, report_data in enumerate(recent_reports, 1):
                company = report_data['company'][:27] + "..." if len(report_data['company']) > 30 else report_data['company']
                date = report_data['date']
                grade = report_data['grade']
                status = "⚠️ Needs Work" if grade < 70 else "✓ Good" if grade >= 80 else "~ Acceptable"
                
                print(f"{i:<3} {company:<30} {date:<12} {grade:<8} {status:<12}")
            
            console.blank()
            
            # Show average grade
            avg_grade = sum(r['grade'] for r in recent_reports) / len(recent_reports)
            console.info(f"Average Quality Grade: {avg_grade:.1f}/100")
            
            # Show any concerning trends
            low_grades = [r for r in recent_reports if r['grade'] < 70]
            if low_grades:
                console.blank()
                console.warn(f"{len(low_grades)} report(s) need attention (grade < 70)")
                for report in low_grades:
                    console.info(f"  • {report['company']}: {report['grade']}/100")
            
            console.blank()
            console.info("Use 'primr --qa \"Company Name\"' for detailed analysis of any report")
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to show recent QA summary: {e}")
            console.error(f"Failed to display QA summary: {e}")
            return 1
    
    def _get_recent_reports_with_qa(self, count: int) -> list[dict]:
        """
        Get recent reports that have QA analysis.
        
        Args:
            count: Maximum number of reports to return
            
        Returns:
            List of report data dictionaries with QA info
        """
        import glob
        from datetime import datetime
        
        if not self.output_dir.exists():
            return []
        
        # Find all QA report files
        qa_files = list(self.output_dir.glob("*QA_Report*.txt"))
        if not qa_files:
            return []
        
        # Sort by modification time, newest first
        qa_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        reports = []
        for qa_file in qa_files[:count]:
            try:
                # Extract company name from QA filename
                filename = qa_file.name
                # Remove "_QA_Report_" and date suffix
                if "_QA_Report_" in filename:
                    company_name = filename.split("_QA_Report_")[0]
                else:
                    continue
                
                # Get file date
                mtime = datetime.fromtimestamp(qa_file.stat().st_mtime)
                
                # Parse QA grade from file content
                content = qa_file.read_text(encoding='utf-8')
                grade = None
                for line in content.split('\n'):
                    if line.startswith('Quality Score:'):
                        # Extract score like "Quality Score: 85/100"
                        parts = line.split(':')[1].strip().split('/')
                        if parts and parts[0].isdigit():
                            grade = int(parts[0])
                            break
                
                if grade is not None:
                    reports.append({
                        'company': company_name.replace('_', ' '),
                        'date': mtime.strftime('%Y-%m-%d'),
                        'grade': grade,
                        'qa_file': qa_file
                    })
                    
            except Exception as e:
                logger.warning(f"Failed to parse QA file {qa_file}: {e}")
                continue
        
        return reports
    
    def _find_qa_report(self, company_name: str) -> Optional[Path]:
        """
        Find the most recent QA report for a company.
        
        Args:
            company_name: Name of company
            
        Returns:
            Path to QA report file, or None if not found
        """
        if not self.output_dir.exists():
            return None
        
        # Clean company name for pattern matching
        clean_name = self.report_loader._clean_company_name_for_search(company_name)
        
        # Try multiple patterns with increasing flexibility
        patterns = [
            f"{company_name}*QA_Report*.txt",  # Exact match first
            f"*{company_name}*QA_Report*.txt",  # Anywhere in filename
            f"{clean_name}*QA_Report*.txt",  # Clean name
            f"*{clean_name}*QA_Report*.txt",  # Clean name anywhere
            "*QA_Report*.txt"  # All QA reports as fallback
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = list(self.output_dir.glob(pattern))
            if matches:
                # If we found matches with this pattern, use them
                all_matches.extend(matches)
                break  # Use first successful pattern
        
        if not all_matches:
            return None
        
        # If we used the fallback pattern, filter by company name similarity
        if len(patterns) > 0 and not any(company_name.lower() in str(match).lower() or clean_name.lower() in str(match).lower() for match in all_matches):
            # Filter matches that contain parts of the company name
            company_words = company_name.lower().split()
            filtered_matches = []
            for match in all_matches:
                match_str = str(match).lower()
                if any(word in match_str for word in company_words if len(word) > 2):
                    filtered_matches.append(match)
            all_matches = filtered_matches if filtered_matches else all_matches
        
        # Remove duplicates and sort by modification time
        unique_matches = list(set(all_matches))
        if not unique_matches:
            return None
            
        latest_file = max(unique_matches, key=lambda f: f.stat().st_mtime)
        
        return latest_file
        
        return latest_file