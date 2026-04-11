"""Figure extraction and caption association utilities for scientific papers."""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pymupdf

from config import PARSED_DIR

logger = logging.getLogger(__name__)


class FigureHandler:
    """Handles figure extraction and caption association from scientific papers."""
    
    def __init__(self) -> None:
        """Initialize the figure handler."""
        pass
    
    def extract_figures(self, pdf_path: Path, filename_stem: str) -> List[Dict[str, Any]]:
        """
        Extract embedded images from a PDF and save as PNG files.
        
        Args:
            pdf_path: Path to the input PDF file
            filename_stem: Stem of the filename for creating output directory
            
        Returns:
            List of dictionaries containing image metadata with keys:
            image_path, page_number, image_index, width, height
        """
        logger.info(f"Extracting figures from {pdf_path.name}")
        
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            logger.error("Expected: PDF file to exist")
            logger.error("Action: ensure PDF file exists")
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Create figures output directory
        figures_dir = PARSED_DIR / f"{filename_stem}_figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        
        extracted_figures = []
        
        try:
            doc = pymupdf.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                logger.debug(f"Found {len(image_list)} images on page {page_num + 1}")
                
                for img_index, img in enumerate(image_list):
                    try:
                        # Extract image data
                        xref = img[0]  # xref number
                        pix = pymupdf.Pixmap(doc, xref)
                        
                        # Skip if image is too small (likely decorative)
                        if pix.width < 50 or pix.height < 50:
                            logger.debug(f"Skipping small image {img_index} on page {page_num + 1} ({pix.width}x{pix.height})")
                            pix = None
                            continue
                        
                        # Convert to RGB if CMYK
                        if pix.n - pix.alpha < 4:  # Not CMYK
                            img_data = pix.tobytes("png")
                        else:  # CMYK
                            pix_rgb = pymupdf.Pixmap(pymupdf.csRGB, pix)
                            img_data = pix_rgb.tobytes("png")
                            pix_rgb = None
                        
                        # Save image
                        image_filename = f"page_{page_num + 1:03d}_img_{img_index:02d}.png"
                        image_path = figures_dir / image_filename
                        
                        with open(image_path, 'wb') as img_file:
                            img_file.write(img_data)
                        
                        # Store metadata
                        figure_info = {
                            "image_path": str(image_path),
                            "page_number": page_num + 1,
                            "image_index": img_index,
                            "width": pix.width,
                            "height": pix.height
                        }
                        extracted_figures.append(figure_info)
                        
                        logger.debug(f"Extracted image {image_filename} ({pix.width}x{pix.height})")
                        
                        pix = None  # Free memory
                        
                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            
            logger.info(f"Successfully extracted {len(extracted_figures)} figures from {pdf_path.name}")
            return extracted_figures
            
        except Exception as e:
            logger.error(f"Failed to extract figures from {pdf_path.name}: {e}")
            logger.error("Expected: successful image extraction from PDF")
            logger.error("Action: check PDF file integrity and PyMuPDF installation")
            return []
    
    def match_captions(self, pdf_path: Path, extracted_figures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Match extracted figures to their captions using proximity heuristics.
        
        Args:
            pdf_path: Path to the input PDF file
            extracted_figures: List of figure metadata from extract_figures()
            
        Returns:
            List of dictionaries with image_path, caption_text, and page_number keys
        """
        logger.info(f"Matching captions for {len(extracted_figures)} figures from {pdf_path.name}")
        
        if not extracted_figures:
            logger.info("No figures to match captions for")
            return []
        
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            logger.error("Expected: PDF file to exist")
            logger.error("Action: ensure PDF file exists")
            return []
        
        figures_with_captions = []
        
        try:
            doc = pymupdf.open(pdf_path)
            
            # Extract text blocks from all pages
            page_text_blocks = {}
            for page_num in range(len(doc)):
                page = doc[page_num]
                text_blocks = page.get_text("dict")["blocks"]
                page_text_blocks[page_num] = text_blocks
            
            # Match each figure to a caption
            for figure in extracted_figures:
                page_num = figure["page_number"] - 1  # Convert to 0-indexed
                caption_text = self._find_nearest_caption(
                    page_text_blocks, 
                    page_num, 
                    figure["image_index"]
                )
                
                figure_with_caption = {
                    "image_path": figure["image_path"],
                    "caption_text": caption_text,
                    "page_number": figure["page_number"]
                }
                figures_with_captions.append(figure_with_caption)
                
                if caption_text:
                    logger.debug(f"Matched caption for figure on page {figure['page_number']}: {caption_text[:100]}...")
                else:
                    logger.debug(f"No caption found for figure on page {figure['page_number']}")
            
            doc.close()
            
            matched_count = sum(1 for fig in figures_with_captions if fig["caption_text"])
            logger.info(f"Successfully matched {matched_count}/{len(figures_with_captions)} figures to captions")
            
            return figures_with_captions
            
        except Exception as e:
            logger.error(f"Failed to match captions for {pdf_path.name}: {e}")
            logger.error("Expected: successful caption matching")
            logger.error("Action: check PDF file integrity and text extraction")
            return []
    
    def process_pdf_figures(self, pdf_path: Path, filename_stem: str) -> List[Dict[str, Any]]:
        """
        Complete figure processing pipeline: extract figures and match captions.
        
        Args:
            pdf_path: Path to the input PDF file
            filename_stem: Stem of the filename for creating output directory
            
        Returns:
            List of dictionaries with image_path, caption_text, and page_number keys
        """
        logger.info(f"Processing figures for {pdf_path.name}")
        
        try:
            # Extract figures
            extracted_figures = self.extract_figures(pdf_path, filename_stem)
            
            if not extracted_figures:
                logger.info(f"No figures found in {pdf_path.name}")
                return []
            
            # Match captions
            figures_with_captions = self.match_captions(pdf_path, extracted_figures)
            
            logger.info(f"Completed figure processing for {pdf_path.name}")
            return figures_with_captions
            
        except Exception as e:
            logger.error(f"Figure processing failed for {pdf_path.name}: {e}")
            logger.error("Expected: successful figure extraction and caption matching")
            logger.error("Action: check PDF file and processing pipeline")
            return []
    
    def _find_nearest_caption(self, page_text_blocks: Dict[int, List[Dict]], target_page: int, image_index: int) -> str:
        """
        Find the nearest caption text for a figure using proximity heuristics.
        
        Args:
            page_text_blocks: Dictionary mapping page numbers to text blocks
            target_page: Page number where the figure is located (0-indexed)
            image_index: Index of the image on the page
            
        Returns:
            Caption text or empty string if no caption found
        """
        # Caption patterns to search for
        caption_patterns = [
            r'(?i)\bfig(?:ure)?\s*\.?\s*\d+',  # Fig. 1, Figure 1, etc.
            r'(?i)\bfig(?:ure)?\s*\d+',       # Fig1, Figure1, etc.
            r'(?i)\bfig(?:ure)?\s*[a-z]',     # Fig a, Figure a, etc.
        ]
        
        # Search on the same page first
        caption_text = self._search_page_for_caption(
            page_text_blocks.get(target_page, []), 
            caption_patterns
        )
        
        if caption_text:
            return caption_text
        
        # Search on adjacent pages if not found on same page
        for page_offset in [1, -1, 2, -2]:  # Check next/prev pages, then further
            search_page = target_page + page_offset
            if search_page in page_text_blocks:
                caption_text = self._search_page_for_caption(
                    page_text_blocks[search_page], 
                    caption_patterns
                )
                if caption_text:
                    logger.debug(f"Found caption on page {search_page + 1} for figure on page {target_page + 1}")
                    return caption_text
        
        return ""
    
    def _search_page_for_caption(self, text_blocks: List[Dict], caption_patterns: List[str]) -> str:
        """
        Search text blocks on a page for caption patterns.
        
        Args:
            text_blocks: List of text block dictionaries from PyMuPDF
            caption_patterns: List of regex patterns to match captions
            
        Returns:
            Caption text or empty string if no caption found
        """
        for block in text_blocks:
            if "lines" not in block:
                continue
            
            # Extract text from block
            block_text = ""
            for line in block["lines"]:
                for span in line.get("spans", []):
                    block_text += span.get("text", "") + " "
            
            block_text = block_text.strip()
            
            # Check if block contains caption pattern
            for pattern in caption_patterns:
                if re.search(pattern, block_text):
                    # Extract caption sentence(s)
                    caption = self._extract_caption_text(block_text, pattern)
                    if caption:
                        return caption
        
        return ""
    
    def _extract_caption_text(self, block_text: str, pattern: str) -> str:
        """
        Extract caption text from a text block containing a caption pattern.
        
        Args:
            block_text: Text block containing the caption
            pattern: Regex pattern that matched the caption
            
        Returns:
            Cleaned caption text
        """
        # Find the caption pattern match
        match = re.search(pattern, block_text)
        if not match:
            return ""
        
        # Extract text starting from the pattern match
        start_pos = match.start()
        caption_text = block_text[start_pos:]
        
        # Clean up the caption text
        caption_text = re.sub(r'\s+', ' ', caption_text)  # Normalize whitespace
        caption_text = caption_text.strip()
        
        # Limit caption length to avoid including unrelated text
        max_caption_length = 500
        if len(caption_text) > max_caption_length:
            # Try to find a sentence boundary
            sentences = re.split(r'[.!?]+', caption_text[:max_caption_length])
            if len(sentences) > 1:
                caption_text = sentences[0] + "."
            else:
                caption_text = caption_text[:max_caption_length] + "..."
        
        return caption_text


# Module-level convenience functions
def extract_figures(pdf_path: Path, filename_stem: str) -> List[Dict[str, Any]]:
    """
    Extract embedded images from a PDF and save as PNG files.
    
    Args:
        pdf_path: Path to the input PDF file
        filename_stem: Stem of the filename for creating output directory
        
    Returns:
        List of dictionaries containing image metadata
    """
    handler = FigureHandler()
    return handler.extract_figures(pdf_path, filename_stem)


def match_captions(pdf_path: Path, extracted_figures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Match extracted figures to their captions using proximity heuristics.
    
    Args:
        pdf_path: Path to the input PDF file
        extracted_figures: List of figure metadata from extract_figures()
        
    Returns:
        List of dictionaries with image_path, caption_text, and page_number keys
    """
    handler = FigureHandler()
    return handler.match_captions(pdf_path, extracted_figures)


def process_pdf_figures(pdf_path: Path, filename_stem: str) -> List[Dict[str, Any]]:
    """
    Complete figure processing pipeline: extract figures and match captions.
    
    Args:
        pdf_path: Path to the input PDF file
        filename_stem: Stem of the filename for creating output directory
        
    Returns:
        List of dictionaries with image_path, caption_text, and page_number keys
    """
    handler = FigureHandler()
    return handler.process_pdf_figures(pdf_path, filename_stem)