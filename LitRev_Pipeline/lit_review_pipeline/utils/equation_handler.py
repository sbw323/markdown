"""Equation detection and LaTeX extraction utilities for scientific papers."""

import base64
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pymupdf

# Optional dependencies
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from config import ANTHROPIC_API_KEY, PIPELINE_MODEL, EQUATION_BACKEND

logger = logging.getLogger(__name__)


class EquationHandler:
    """Handles equation detection and LaTeX extraction from scientific papers."""
    
    def __init__(self) -> None:
        """Initialize the equation handler."""
        self.anthropic_client = None
        
        if ANTHROPIC_API_KEY and Anthropic:
            self.anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
        elif not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set - Claude vision fallback unavailable")
        elif not Anthropic:
            logger.warning("anthropic package not installed - Claude vision fallback unavailable")
    
    def equation_density_score(self, page_text: str) -> float:
        """
        Calculate equation density score for a page based on garbled text and LaTeX fragments.
        
        Args:
            page_text: Text content of the page
            
        Returns:
            Float score between 0.0 and 1.0, where higher values indicate more equations
        """
        if not page_text.strip():
            return 0.0
        
        # Count garbled text patterns (common in equation-heavy pages)
        garbled_patterns = [
            r'[^\w\s]{3,}',  # 3+ consecutive non-alphanumeric chars
            r'\b[a-zA-Z]{1,2}\d+[a-zA-Z]*\b',  # Variable-like patterns (x1, a2b, etc.)
            r'[=<>≤≥≠±∞∑∏∫∂∇]+',  # Mathematical symbols
            r'\b[A-Z]{2,}\b(?![A-Z])',  # Uppercase sequences (often garbled)
        ]
        
        garbled_count = 0
        for pattern in garbled_patterns:
            garbled_count += len(re.findall(pattern, page_text))
        
        # Count partial LaTeX fragments
        latex_patterns = [
            r'\$[^$]*\$',  # Inline math
            r'\$\$[^$]*\$\$',  # Display math
            r'\\[a-zA-Z]+\{[^}]*\}',  # LaTeX commands
            r'\\[a-zA-Z]+',  # LaTeX commands without braces
            r'\{[^}]*\}',  # Braces (common in equations)
            r'_\{[^}]*\}',  # Subscripts
            r'\^\{[^}]*\}',  # Superscripts
        ]
        
        latex_count = 0
        for pattern in latex_patterns:
            latex_count += len(re.findall(pattern, page_text))
        
        # Calculate text-to-whitespace ratio
        total_chars = len(page_text)
        whitespace_chars = len(re.findall(r'\s', page_text))
        text_chars = total_chars - whitespace_chars
        
        if total_chars == 0:
            whitespace_ratio = 0.0
        else:
            whitespace_ratio = whitespace_chars / total_chars
        
        # Calculate normalized scores
        text_length = len(page_text.split())
        if text_length == 0:
            return 0.0
        
        garbled_score = min(garbled_count / text_length, 1.0)
        latex_score = min(latex_count / text_length, 1.0)
        gap_score = min(whitespace_ratio * 2, 1.0)  # Amplify whitespace impact
        
        # Weighted combination
        density_score = (0.4 * garbled_score + 0.4 * latex_score + 0.2 * gap_score)
        
        return min(density_score, 1.0)
    
    def nougat_extract(self, pdf_path: Path, page_numbers: List[int]) -> Optional[str]:
        """
        Extract LaTeX equations from specific pages using Nougat OCR.
        
        Args:
            pdf_path: Path to the PDF file
            page_numbers: List of page numbers to process (0-indexed)
            
        Returns:
            Markdown content with LaTeX equations or None if extraction fails
        """
        if not page_numbers:
            return None
        
        logger.info(f"Running Nougat extraction on {len(page_numbers)} pages from {pdf_path.name}")
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                output_path = temp_path / "nougat_output"
                
                # Prepare Nougat command
                cmd = [
                    "nougat",
                    str(pdf_path),
                    "-o", str(output_path),
                    "--pages", ",".join(map(str, page_numbers)),
                    "--markdown"
                ]
                
                # Run Nougat
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode != 0:
                    logger.error(f"Nougat failed with return code {result.returncode}")
                    logger.error(f"Stderr: {result.stderr}")
                    return None
                
                # Find output file
                output_files = list(output_path.glob("*.mmd"))
                if not output_files:
                    logger.error("No Nougat output file found")
                    return None
                
                # Read output
                with open(output_files[0], 'r', encoding='utf-8') as f:
                    nougat_content = f.read()
                
                # Normalize equation delimiters
                normalized_content = self._normalize_equation_delimiters(nougat_content)
                
                logger.info(f"Successfully extracted content via Nougat from {len(page_numbers)} pages")
                return normalized_content
                
        except subprocess.TimeoutExpired:
            logger.error("Nougat extraction timed out")
            return None
        except Exception as e:
            logger.error(f"Nougat extraction failed: {e}")
            return None
    
    def claude_vision_extract(self, pdf_path: Path, page_numbers: List[int]) -> Optional[str]:
        """
        Extract LaTeX equations from specific pages using Claude vision API.
        
        Args:
            pdf_path: Path to the PDF file
            page_numbers: List of page numbers to process (0-indexed)
            
        Returns:
            Markdown content with LaTeX equations or None if extraction fails
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not available for Claude vision extraction")
            return None
        
        if not page_numbers:
            return None
        
        logger.info(f"Running Claude vision extraction on {len(page_numbers)} pages from {pdf_path.name}")
        
        try:
            doc = pymupdf.open(pdf_path)
            extracted_pages = []
            
            for page_num in page_numbers:
                if page_num >= len(doc):
                    logger.warning(f"Page {page_num} does not exist in {pdf_path.name}")
                    continue
                
                # Render page at 300 DPI
                page = doc[page_num]
                mat = pymupdf.Matrix(300/72, 300/72)  # 300 DPI scaling
                pix = page.get_pixmap(matrix=mat)
                png_data = pix.tobytes("png")
                
                # Encode for API
                image_b64 = base64.b64encode(png_data).decode('utf-8')
                
                # Prepare prompt
                prompt = """
                Please extract all mathematical equations and formulas from this page and convert them to LaTeX format.
                
                Return the content as Markdown with:
                - Regular text preserved as-is
                - Inline equations wrapped in $...$
                - Display equations wrapped in $$...$$
                - Each equation prefixed with [EQUATION] tag
                
                Focus on mathematical content and preserve the LaTeX formatting exactly.
                If there are no equations on this page, return "No equations found."
                """
                
                # Call Claude API
                response = self.anthropic_client.messages.create(
                    model=PIPELINE_MODEL,
                    max_tokens=2000,
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
                
                page_content = response.content[0].text.strip()
                if page_content and page_content != "No equations found.":
                    extracted_pages.append(f"## Page {page_num + 1}\n\n{page_content}")
            
            doc.close()
            
            if not extracted_pages:
                return None
            
            combined_content = "\n\n".join(extracted_pages)
            normalized_content = self._normalize_equation_delimiters(combined_content)
            
            logger.info(f"Successfully extracted content via Claude vision from {len(page_numbers)} pages")
            return normalized_content
            
        except Exception as e:
            logger.error(f"Claude vision extraction failed: {e}")
            return None
    
    def merge_extractions(self, base_markdown: str, equation_markdown: Optional[str]) -> str:
        """
        Merge base PyMuPDF4LLM Markdown with equation-enhanced Markdown.
        
        Args:
            base_markdown: Original Markdown from PyMuPDF4LLM
            equation_markdown: Equation-enhanced Markdown from Nougat/Claude
            
        Returns:
            Merged Markdown with enhanced equation content
        """
        if not equation_markdown:
            return base_markdown
        
        logger.info("Merging base Markdown with equation-enhanced content")
        
        # Extract equations from equation_markdown
        equations = self._extract_equations(equation_markdown)
        
        if not equations:
            logger.info("No equations found in enhanced content, returning base Markdown")
            return base_markdown
        
        # Enhance base markdown with equations
        enhanced_markdown = self._enhance_with_equations(base_markdown, equations)
        
        logger.info(f"Successfully merged content with {len(equations)} equations")
        return enhanced_markdown
    
    def process_pdf_equations(self, pdf_path: Path, base_markdown: str) -> str:
        """
        Process a PDF for equation extraction based on configured backend.
        
        Args:
            pdf_path: Path to the PDF file
            base_markdown: Base Markdown content from PyMuPDF4LLM
            
        Returns:
            Enhanced Markdown with equations or original if no enhancement
        """
        if EQUATION_BACKEND == "none":
            logger.info("Equation backend disabled, returning base Markdown")
            return base_markdown
        
        logger.info(f"Processing equations for {pdf_path.name} using backend: {EQUATION_BACKEND}")
        
        # Analyze pages for equation density
        equation_pages = self._identify_equation_pages(pdf_path)
        
        if not equation_pages:
            logger.info("No equation-heavy pages detected")
            return base_markdown
        
        logger.info(f"Detected {len(equation_pages)} equation-heavy pages: {equation_pages}")
        
        equation_markdown = None
        
        if EQUATION_BACKEND == "nougat":
            equation_markdown = self.nougat_extract(pdf_path, equation_pages)
        elif EQUATION_BACKEND == "claude_vision":
            equation_markdown = self.claude_vision_extract(pdf_path, equation_pages)
        elif EQUATION_BACKEND == "both":
            # Try Nougat first, fallback to Claude
            equation_markdown = self.nougat_extract(pdf_path, equation_pages)
            if not equation_markdown:
                equation_markdown = self.claude_vision_extract(pdf_path, equation_pages)
        
        return self.merge_extractions(base_markdown, equation_markdown)
    
    def _identify_equation_pages(self, pdf_path: Path, threshold: float = 0.3) -> List[int]:
        """
        Identify pages with high equation density.
        
        Args:
            pdf_path: Path to the PDF file
            threshold: Minimum density score to consider a page equation-heavy
            
        Returns:
            List of page numbers (0-indexed) with high equation density
        """
        try:
            doc = pymupdf.open(pdf_path)
            equation_pages = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                
                density = self.equation_density_score(page_text)
                if density >= threshold:
                    equation_pages.append(page_num)
                    logger.debug(f"Page {page_num + 1} equation density: {density:.3f}")
            
            doc.close()
            return equation_pages
            
        except Exception as e:
            logger.error(f"Failed to analyze equation density for {pdf_path.name}: {e}")
            return []
    
    def _normalize_equation_delimiters(self, content: str) -> str:
        """
        Normalize equation delimiters to consistent format with [EQUATION] tags.
        
        Args:
            content: Content with various equation delimiter formats
            
        Returns:
            Content with normalized delimiters
        """
        # Add [EQUATION] prefix to display equations
        content = re.sub(r'\$\$([^$]+)\$\$', r'[EQUATION] $$\1$$', content)
        
        # Add [EQUATION] prefix to inline equations
        content = re.sub(r'(?<!\$)\$([^$]+)\$(?!\$)', r'[EQUATION] $\1$', content)
        
        # Handle other LaTeX environments
        latex_envs = ['equation', 'align', 'gather', 'multline', 'eqnarray']
        for env in latex_envs:
            pattern = rf'\\begin\{{{env}\*?\}}(.*?)\\end\{{{env}\*?\}}'
            replacement = rf'[EQUATION] $$\1$$'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        return content
    
    def _extract_equations(self, equation_markdown: str) -> List[Dict[str, str]]:
        """
        Extract equations from equation-enhanced Markdown.
        
        Args:
            equation_markdown: Markdown content with equations
            
        Returns:
            List of equation dictionaries with 'type' and 'content' keys
        """
        equations = []
        
        # Extract display equations
        display_pattern = r'\[EQUATION\]\s*\$\$([^$]+)\$\$'
        for match in re.finditer(display_pattern, equation_markdown):
            equations.append({
                'type': 'display',
                'content': match.group(1).strip()
            })
        
        # Extract inline equations
        inline_pattern = r'\[EQUATION\]\s*\$([^$]+)\$'
        for match in re.finditer(inline_pattern, equation_markdown):
            equations.append({
                'type': 'inline',
                'content': match.group(1).strip()
            })
        
        return equations
    
    def _enhance_with_equations(self, base_markdown: str, equations: List[Dict[str, str]]) -> str:
        """
        Enhance base Markdown with extracted equations.
        
        Args:
            base_markdown: Original Markdown content
            equations: List of equation dictionaries
            
        Returns:
            Enhanced Markdown with equations integrated
        """
        enhanced = base_markdown
        
        # Simple strategy: append equations at the end in a dedicated section
        if equations:
            enhanced += "\n\n## Extracted Equations\n\n"
            
            for i, eq in enumerate(equations, 1):
                if eq['type'] == 'display':
                    enhanced += f"[EQUATION] $${eq['content']}$$\n\n"
                else:
                    enhanced += f"[EQUATION] ${eq['content']}$\n\n"
        
        return enhanced


# Module-level convenience functions
def equation_density_score(page_text: str) -> float:
    """
    Calculate equation density score for a page.
    
    Args:
        page_text: Text content of the page
        
    Returns:
        Float score between 0.0 and 1.0
    """
    handler = EquationHandler()
    return handler.equation_density_score(page_text)


def nougat_extract(pdf_path: Path, page_numbers: List[int]) -> Optional[str]:
    """
    Extract LaTeX equations using Nougat OCR.
    
    Args:
        pdf_path: Path to the PDF file
        page_numbers: List of page numbers to process
        
    Returns:
        Markdown content with LaTeX equations or None
    """
    handler = EquationHandler()
    return handler.nougat_extract(pdf_path, page_numbers)


def claude_vision_extract(pdf_path: Path, page_numbers: List[int]) -> Optional[str]:
    """
    Extract LaTeX equations using Claude vision API.
    
    Args:
        pdf_path: Path to the PDF file
        page_numbers: List of page numbers to process
        
    Returns:
        Markdown content with LaTeX equations or None
    """
    handler = EquationHandler()
    return handler.claude_vision_extract(pdf_path, page_numbers)


def merge_extractions(base_markdown: str, equation_markdown: Optional[str]) -> str:
    """
    Merge base Markdown with equation-enhanced Markdown.
    
    Args:
        base_markdown: Original Markdown from PyMuPDF4LLM
        equation_markdown: Equation-enhanced Markdown
        
    Returns:
        Merged Markdown with enhanced equations
    """
    handler = EquationHandler()
    return handler.merge_extractions(base_markdown, equation_markdown)