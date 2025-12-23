"""
Report loader for QA analysis.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import ReportContent, ReportMetadata

logger = logging.getLogger(__name__)


class ReportLoader:
    """Loads reports from workspace for QA analysis."""
    
    def __init__(self):
        """Initialize report loader."""
        self.output_dir = Path("output")
    
    def find_latest_report(self, company_name: str) -> Optional[Path]:
        """
        Find most recent report for company.
        
        Args:
            company_name: Name of company to find report for
            
        Returns:
            Path to most recent report file, or None if not found
        """
        if not self.output_dir.exists():
            logger.warning("Output directory does not exist")
            return None
        
        # Clean company name for pattern matching
        clean_name = self._clean_company_name_for_search(company_name)
        
        # Try multiple patterns in order of preference
        patterns = [
            f"{clean_name}*Strategic_Overview*.txt",
            f"{clean_name}*Company_Overview*.txt", 
            f"{clean_name}*AI_Strategy*.txt",
            f"*{clean_name}*Strategic_Overview*.txt",
            f"*{clean_name}*Company_Overview*.txt",
            f"*{clean_name}*AI_Strategy*.txt"
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = list(self.output_dir.glob(pattern))
            all_matches.extend(matches)
        
        if not all_matches:
            logger.warning(f"No reports found for company: {company_name}")
            return None
        
        # Remove duplicates and sort by modification time
        unique_matches = list(set(all_matches))
        latest_file = max(unique_matches, key=lambda f: f.stat().st_mtime)
        
        logger.info(f"Found latest report for {company_name}: {latest_file.name}")
        return latest_file
    
    def _clean_company_name_for_search(self, company_name: str) -> str:
        """Clean company name for file pattern matching."""
        # Remove common suffixes and clean for file system
        clean = company_name.strip()
        
        # Remove common corporate suffixes for better matching
        suffixes = [" Inc", " Inc.", " LLC", " Ltd", " Ltd.", " Corp", " Corp.", " Corporation"]
        for suffix in suffixes:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)].strip()
        
        # Replace problematic characters for file system and glob patterns
        clean = clean.replace("/", "_").replace("\\", "_").replace(":", "_")
        clean = clean.replace("&", "and").replace(",", "").replace("*", "_")
        clean = clean.replace("?", "_").replace("<", "_").replace(">", "_")
        clean = clean.replace("|", "_").replace('"', "_").replace("'", "_")
        
        # Remove any remaining problematic characters
        import re
        clean = re.sub(r'[^\w\s\-\.]', '_', clean)
        
        # Collapse multiple underscores and spaces
        clean = re.sub(r'[_\s]+', '_', clean).strip('_')
        
        # Ensure we have something to search with
        if not clean or len(clean.strip()) == 0:
            clean = "unknown_company"
        
        return clean
    
    def load_report_from_path(self, report_path: Path) -> Optional[ReportContent]:
        """
        Load report content from specific path.
        
        Args:
            report_path: Path to report file
            
        Returns:
            ReportContent object or None if loading fails
        """
        if not report_path.exists():
            logger.error(f"Report file does not exist: {report_path}")
            return None
        
        try:
            # Handle different file formats
            if report_path.suffix.lower() == '.txt':
                content = self._load_txt_file(report_path)
            elif report_path.suffix.lower() == '.md':
                content = self._load_txt_file(report_path)  # Markdown is text-based
            elif report_path.suffix.lower() == '.docx':
                content = self._load_docx_file(report_path)
            elif report_path.suffix.lower() == '.pdf':
                content = self._load_pdf_file(report_path)
            else:
                logger.warning(f"Unsupported file format: {report_path.suffix}")
                return None
            
            if not content:
                logger.error(f"Could not extract content from: {report_path}")
                return None
            
            # Extract company name from filename
            company_name = self._extract_company_name(report_path.name)
            
            # Parse sections
            sections = self._parse_sections(content)
            
            # Extract citations
            citations = self._extract_citations(content)
            
            # Create metadata
            metadata = self._extract_metadata(report_path, company_name)
            
            return ReportContent(
                company_name=company_name,
                content=content,
                sections=sections,
                citations=citations,
                metadata=metadata,
                file_path=report_path
            )
            
        except Exception as e:
            logger.error(f"Failed to load report {report_path}: {e}")
            return None
    
    def _load_txt_file(self, file_path: Path) -> str:
        """Load content from text file."""
        return file_path.read_text(encoding='utf-8')
    
    def _load_docx_file(self, file_path: Path) -> Optional[str]:
        """Load content from DOCX file."""
        try:
            # Try to import docx library
            try:
                from docx import Document
            except ImportError:
                logger.warning("python-docx not available, cannot read DOCX files")
                return None
            
            doc = Document(file_path)
            paragraphs = []
            
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    paragraphs.append(paragraph.text)
            
            return '\n'.join(paragraphs)
            
        except Exception as e:
            logger.error(f"Failed to read DOCX file {file_path}: {e}")
            return None
    
    def _load_pdf_file(self, file_path: Path) -> Optional[str]:
        """Load content from PDF file."""
        try:
            # Try to import PDF library
            try:
                import PyPDF2
            except ImportError:
                logger.warning("PyPDF2 not available, cannot read PDF files")
                return None
            
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text_content = []
                
                for page in pdf_reader.pages:
                    text_content.append(page.extract_text())
                
                return '\n'.join(text_content)
                
        except Exception as e:
            logger.error(f"Failed to read PDF file {file_path}: {e}")
            return None
    
    def load_report_content(self, company_name: str) -> Optional[ReportContent]:
        """
        Load report content for company.
        
        Args:
            company_name: Name of company
            
        Returns:
            ReportContent object or None if not found
        """
        report_path = self.find_latest_report(company_name)
        if not report_path:
            return None
        
        return self.load_report_from_path(report_path)
    
    def _extract_company_name(self, filename: str) -> str:
        """Extract company name from filename."""
        # Remove file extension
        name = filename.replace('.txt', '').replace('.docx', '').replace('.pdf', '')
        
        # Remove common suffixes
        suffixes = ['_Company_Overview', '_Strategic_Overview', '_AI_Strategy']
        for suffix in suffixes:
            if suffix in name:
                name = name.split(suffix)[0]
                break
        
        # Remove date patterns
        name = re.sub(r'_\d{2}-\d{2}-\d{4}.*$', '', name)
        name = re.sub(r'_\d{8}_\d{6}.*$', '', name)
        
        return name.strip()
    
    def _parse_sections(self, content: str) -> Dict[str, str]:
        """Parse content into sections based on headers."""
        sections = {}
        
        # Split by common header patterns
        lines = content.split('\n')
        current_section = "Introduction"
        current_content = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip empty lines for header detection
            if not line_stripped:
                current_content.append(line)
                continue
            
            # Check if line is a header
            is_header = False
            
            # Markdown headers (# ## ###)
            if line_stripped.startswith('#'):
                is_header = True
                header_text = line_stripped.lstrip('#').strip()
            
            # All caps headers (but not too long)
            elif (line_stripped.isupper() and 
                  len(line_stripped) > 3 and 
                  len(line_stripped) < 100 and
                  not line_stripped.startswith('HTTP')):  # Avoid URLs
                is_header = True
                header_text = line_stripped
            
            # Numbered headers (1. 2. etc.)
            elif re.match(r'^\d+\.\s+[A-Z]', line_stripped):
                is_header = True
                header_text = line_stripped
            
            # Title case headers (longer than 10 chars, starts with capital)
            elif (len(line_stripped) > 10 and 
                  line_stripped[0].isupper() and
                  not line_stripped.endswith('.') and  # Not a sentence
                  sum(1 for c in line_stripped if c.isupper()) >= 2):  # Multiple caps
                is_header = True
                header_text = line_stripped
            
            if is_header:
                # Save previous section
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                
                # Start new section
                current_section = header_text
                current_content = []
            else:
                current_content.append(line)
        
        # Save final section
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()
        
        # Remove empty sections
        sections = {k: v for k, v in sections.items() if v.strip()}
        
        return sections
    
    def _extract_citations(self, content: str) -> List[str]:
        """Extract citations from content."""
        citations = []
        
        # Look for URLs
        url_pattern = r'https?://[^\s\])]+'
        urls = re.findall(url_pattern, content)
        citations.extend(urls)
        
        # Look for numbered citations like [1], [2], etc.
        numbered_citations = re.findall(r'\[\d+\]', content)
        citations.extend(numbered_citations)
        
        return list(set(citations))  # Remove duplicates
    
    def _extract_metadata(self, report_path: Path, company_name: str) -> ReportMetadata:
        """Extract metadata from report path and content."""
        # Extract date from filename
        date_match = re.search(r'(\d{2}-\d{2}-\d{4})', report_path.name)
        if date_match:
            try:
                generation_date = datetime.strptime(date_match.group(1), '%m-%d-%Y')
            except ValueError:
                generation_date = datetime.fromtimestamp(report_path.stat().st_mtime)
        else:
            generation_date = datetime.fromtimestamp(report_path.stat().st_mtime)
        
        # Determine generation mode from filename/content
        generation_mode = "unknown"
        if "Strategic_Overview" in report_path.name:
            generation_mode = "full"
        elif "Company_Overview" in report_path.name:
            generation_mode = "scrape"
        
        return ReportMetadata(
            company_name=company_name,
            generation_date=generation_date,
            generation_mode=generation_mode,
            model_used="unknown",  # Would need to be passed from generation
            file_path=report_path
        )