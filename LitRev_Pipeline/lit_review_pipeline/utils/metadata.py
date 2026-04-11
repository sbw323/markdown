"""Metadata extraction utilities for scientific papers."""

import base64
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import xml.etree.ElementTree as ET

import requests
import pymupdf

# Optional dependency for Anthropic API
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from config import GROBID_URL, ANTHROPIC_API_KEY, PIPELINE_MODEL

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extracts metadata from scientific papers using GROBID with Claude vision fallback."""
    
    def __init__(self) -> None:
        """Initialize the metadata extractor."""
        self.grobid_url = GROBID_URL
        self.anthropic_client = None
        
        if ANTHROPIC_API_KEY and Anthropic:
            self.anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
        elif not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set - Claude vision fallback unavailable")
        elif not Anthropic:
            logger.warning("anthropic package not installed - Claude vision fallback unavailable")
    
    def extract_metadata(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from a PDF file using GROBID with Claude vision fallback.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing extracted metadata with keys:
            filename, title, authors, year, journal, doi, abstract
        """
        logger.info(f"Extracting metadata from {pdf_path.name}")
        
        # Initialize default metadata
        metadata = {
            "filename": pdf_path.name,
            "title": "",
            "authors": [],
            "year": None,
            "journal": "",
            "doi": "",
            "abstract": ""
        }
        
        try:
            # Try GROBID first
            grobid_metadata = self._extract_with_grobid(pdf_path)
            if grobid_metadata:
                metadata.update(grobid_metadata)
                logger.info(f"Successfully extracted metadata via GROBID for {pdf_path.name}")
                return metadata
        except Exception as e:
            logger.warning(f"GROBID extraction failed for {pdf_path.name}: {e}")
        
        try:
            # Fallback to Claude vision
            if self.anthropic_client:
                claude_metadata = self._extract_with_claude_vision(pdf_path)
                if claude_metadata:
                    metadata.update(claude_metadata)
                    logger.info(f"Successfully extracted metadata via Claude vision for {pdf_path.name}")
                    return metadata
        except Exception as e:
            logger.warning(f"Claude vision extraction failed for {pdf_path.name}: {e}")
        
        logger.error(f"All metadata extraction methods failed for {pdf_path.name}")
        return metadata
    
    def _extract_with_grobid(self, pdf_path: Path) -> Optional[Dict[str, Any]]:
        """
        Extract metadata using GROBID service.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with extracted metadata or None if extraction fails
        """
        try:
            with open(pdf_path, 'rb') as pdf_file:
                files = {'input': pdf_file}
                response = requests.post(
                    f"{self.grobid_url}/api/processHeaderDocument",
                    files=files,
                    timeout=30
                )
                response.raise_for_status()
                
                tei_xml = response.text
                return self._parse_tei_xml(tei_xml)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"GROBID request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"GROBID processing error: {e}")
            return None
    
    def _parse_tei_xml(self, tei_xml: str) -> Dict[str, Any]:
        """
        Parse TEI-XML output from GROBID to extract metadata.
        
        Args:
            tei_xml: TEI-XML string from GROBID
            
        Returns:
            Dictionary with extracted metadata
        """
        metadata = {
            "title": "",
            "authors": [],
            "year": None,
            "journal": "",
            "doi": "",
            "abstract": ""
        }
        
        try:
            root = ET.fromstring(tei_xml)
            
            # Define namespace
            ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
            
            # Extract title
            title_elem = root.find('.//tei:titleStmt/tei:title', ns)
            if title_elem is not None and title_elem.text:
                metadata["title"] = title_elem.text.strip()
            
            # Extract authors
            authors = []
            author_elems = root.findall('.//tei:sourceDesc//tei:author', ns)
            for author_elem in author_elems:
                forename_elem = author_elem.find('.//tei:forename', ns)
                surname_elem = author_elem.find('.//tei:surname', ns)
                
                forename = forename_elem.text.strip() if forename_elem is not None and forename_elem.text else ""
                surname = surname_elem.text.strip() if surname_elem is not None and surname_elem.text else ""
                
                if forename or surname:
                    full_name = f"{forename} {surname}".strip()
                    authors.append(full_name)
            
            metadata["authors"] = authors
            
            # Extract publication year
            date_elem = root.find('.//tei:sourceDesc//tei:date[@when]', ns)
            if date_elem is not None:
                date_when = date_elem.get('when', '')
                if date_when and len(date_when) >= 4:
                    try:
                        metadata["year"] = int(date_when[:4])
                    except ValueError:
                        pass
            
            # Extract journal
            journal_elem = root.find('.//tei:sourceDesc//tei:title[@level="j"]', ns)
            if journal_elem is not None and journal_elem.text:
                metadata["journal"] = journal_elem.text.strip()
            
            # Extract DOI
            doi_elem = root.find('.//tei:sourceDesc//tei:idno[@type="DOI"]', ns)
            if doi_elem is not None and doi_elem.text:
                metadata["doi"] = doi_elem.text.strip()
            
            # Extract abstract
            abstract_elem = root.find('.//tei:profileDesc//tei:abstract/tei:div/tei:p', ns)
            if abstract_elem is not None and abstract_elem.text:
                metadata["abstract"] = abstract_elem.text.strip()
            
            return metadata
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse TEI-XML: {e}")
            return metadata
        except Exception as e:
            logger.error(f"Error parsing TEI-XML: {e}")
            return metadata
    
    def _extract_with_claude_vision(self, pdf_path: Path) -> Optional[Dict[str, Any]]:
        """
        Extract metadata using Claude vision API on the first page of the PDF.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with extracted metadata or None if extraction fails
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available for Claude vision extraction")
            return None
        
        try:
            # Render first page as PNG
            png_data = self._render_first_page_as_png(pdf_path)
            if not png_data:
                return None
            
            # Encode image for API
            image_b64 = base64.b64encode(png_data).decode('utf-8')
            
            # Prepare prompt
            prompt = """
            Please extract the following metadata from this scientific paper's first page:
            - title: The paper's title
            - authors: List of author names
            - year: Publication year (as integer)
            - journal: Journal or venue name
            - doi: DOI if present
            - abstract: Abstract text if visible
            
            Return the result as a JSON object with these exact keys. If any field is not found, use appropriate empty values (empty string for text, empty list for authors, null for year).
            Preserve any LaTeX equations exactly as they appear, wrapped in $ or $$ delimiters.
            """
            
            # Call Claude API
            response = self.anthropic_client.messages.create(
                model=PIPELINE_MODEL,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64
                                }
                            }
                        ]
                    }
                ]
            )
            
            # Parse response
            response_text = response.content[0].text.strip()
            
            # Extract JSON from response (handle potential markdown formatting)
            if "" in response_text:
                json_start = response_text.find("") + 7
                json_end = response_text.find("", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "" in response_text:
                json_start = response_text.find("") + 3
                json_end = response_text.find("", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text
            
            metadata = json.loads(json_text)
            
            # Validate and clean metadata
            cleaned_metadata = {
                "title": str(metadata.get("title", "")),
                "authors": list(metadata.get("authors", [])),
                "year": metadata.get("year"),
                "journal": str(metadata.get("journal", "")),
                "doi": str(metadata.get("doi", "")),
                "abstract": str(metadata.get("abstract", ""))
            }
            
            # Ensure year is int or None
            if cleaned_metadata["year"] is not None:
                try:
                    cleaned_metadata["year"] = int(cleaned_metadata["year"])
                except (ValueError, TypeError):
                    cleaned_metadata["year"] = None
            
            return cleaned_metadata
            
        except Exception as e:
            logger.error(f"Claude vision extraction error: {e}")
            return None
    
    def _render_first_page_as_png(self, pdf_path: Path) -> Optional[bytes]:
        """
        Render the first page of a PDF as PNG bytes.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            PNG image data as bytes or None if rendering fails
        """
        try:
            doc = pymupdf.open(pdf_path)
            if len(doc) == 0:
                logger.error(f"PDF {pdf_path.name} has no pages")
                return None
            
            # Render first page at 150 DPI for good quality
            page = doc[0]
            mat = pymupdf.Matrix(150/72, 150/72)  # 150 DPI scaling
            pix = page.get_pixmap(matrix=mat)
            png_data = pix.tobytes("png")
            
            doc.close()
            return png_data
            
        except Exception as e:
            logger.error(f"Failed to render PDF {pdf_path.name} as PNG: {e}")
            return None