"""
PDF parsing pipeline stage using PyMuPDF4LLM with equation enhancement.

Loads manifest.json and extracts Markdown content from each PDF using PyMuPDF4LLM.
Then enhances equation-heavy pages using the configured equation backend.
Outputs merged Markdown files to data/parsed/ directory.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

import pymupdf4llm

from config import DATA_DIR, PDFS_DIR, PARSED_DIR, EQUATION_BACKEND
from utils.equation_handler import EquationHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_manifest() -> List[Dict[str, Any]]:
    """
    Load the manifest.json file containing PDF metadata.
    
    Returns:
        List of manifest entries with PDF metadata
        
    Raises:
        FileNotFoundError: If manifest.json does not exist
        json.JSONDecodeError: If manifest.json is not valid JSON
    """
    manifest_path = DATA_DIR / "manifest.json"
    
    if not manifest_path.exists():
        logger.error(f"Manifest file not found: {manifest_path}")
        logger.error("Expected: manifest.json created by 01_ingest.py")
        logger.error("Action: run 01_ingest.py first to generate the manifest")
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_entries = json.load(f)
        
        logger.info(f"Loaded manifest with {len(manifest_entries)} entries")
        return manifest_entries
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in manifest file: {e}")
        logger.error("Expected: valid JSON format")
        logger.error("Action: check manifest.json file integrity or regenerate with 01_ingest.py")
        raise


def parse_pdf_to_markdown(pdf_path: Path) -> str:
    """
    Parse a single PDF file to Markdown using PyMuPDF4LLM (Pass 1).
    
    Args:
        pdf_path: Path to the input PDF file
        
    Returns:
        Markdown content from PyMuPDF4LLM
        
    Raises:
        Exception: If PDF parsing fails
    """
    logger.info(f"Pass 1: Parsing {pdf_path.name} with PyMuPDF4LLM")
    
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        logger.error("Expected: PDF file to exist in pdfs directory")
        logger.error("Action: ensure PDF file exists or update manifest")
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Extract Markdown using PyMuPDF4LLM
    markdown_content = pymupdf4llm.to_markdown(str(pdf_path))
    
    logger.info(f"Pass 1 completed for {pdf_path.name}")
    return markdown_content


def enhance_equations(pdf_path: Path, base_markdown: str) -> str:
    """
    Enhance equations in Markdown using the configured equation backend (Pass 2).
    
    Args:
        pdf_path: Path to the input PDF file
        base_markdown: Base Markdown content from PyMuPDF4LLM
        
    Returns:
        Enhanced Markdown with equations or original if backend is 'none'
    """
    if EQUATION_BACKEND == "none":
        logger.info(f"Pass 2: Skipping equation enhancement for {pdf_path.name} (backend: none)")
        return base_markdown
    
    logger.info(f"Pass 2: Enhancing equations for {pdf_path.name} (backend: {EQUATION_BACKEND})")
    
    try:
        equation_handler = EquationHandler()
        enhanced_markdown = equation_handler.process_pdf_equations(pdf_path, base_markdown)
        
        logger.info(f"Pass 2 completed for {pdf_path.name}")
        return enhanced_markdown
        
    except Exception as e:
        logger.error(f"Pass 2 failed for {pdf_path.name}: {e}")
        logger.error("Falling back to Pass 1 output")
        return base_markdown


def save_merged_markdown(content: str, output_path: Path) -> None:
    """
    Save the merged Markdown content to file.
    
    Args:
        content: Markdown content to save
        output_path: Path where the Markdown output should be saved
        
    Raises:
        Exception: If file writing fails
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save Markdown content
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Saved merged Markdown to {output_path.name}")


def process_single_pdf(pdf_path: Path, output_path: Path) -> bool:
    """
    Process a single PDF through both parsing passes.
    
    Args:
        pdf_path: Path to the input PDF file
        output_path: Path where the merged Markdown should be saved
        
    Returns:
        True if processing succeeded, False otherwise
    """
    try:
        # Pass 1: PyMuPDF4LLM extraction
        base_markdown = parse_pdf_to_markdown(pdf_path)
        
        # Pass 2: Equation enhancement
        merged_markdown = enhance_equations(pdf_path, base_markdown)
        
        # Save merged output
        save_merged_markdown(merged_markdown, output_path)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to process {pdf_path.name}: {e}")
        return False


def process_all_pdfs(manifest_entries: List[Dict[str, Any]]) -> None:
    """
    Process all PDF files from the manifest through both parsing passes.
    
    Args:
        manifest_entries: List of manifest entries containing PDF metadata
    """
    logger.info(f"Processing {len(manifest_entries)} PDF files through parsing pipeline")
    logger.info(f"Equation backend configured: {EQUATION_BACKEND}")
    
    successful_count = 0
    failed_count = 0
    
    for entry in manifest_entries:
        filename = entry.get("filename", "")
        if not filename:
            logger.warning("Manifest entry missing filename - skipping")
            failed_count += 1
            continue
        
        # Construct paths
        pdf_path = PDFS_DIR / filename
        filename_stem = Path(filename).stem
        output_path = PARSED_DIR / f"{filename_stem}_merged.md"
        
        # Process PDF through both passes
        if process_single_pdf(pdf_path, output_path):
            successful_count += 1
        else:
            logger.error("Continuing with next PDF file")
            failed_count += 1
    
    logger.info(f"Parsing pipeline completed: {successful_count} successful, {failed_count} failed")


def main() -> None:
    """Main pipeline execution function."""
    logger.info("Starting PDF parsing pipeline with equation enhancement")
    
    try:
        # Load manifest
        manifest_entries = load_manifest()
        
        if not manifest_entries:
            logger.warning("No entries in manifest - pipeline completed with no processing")
            return
        
        # Process all PDFs through both passes
        process_all_pdfs(manifest_entries)
        
        logger.info("PDF parsing pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        logger.error("Expected: successful Markdown extraction and equation enhancement for all PDFs")
        logger.error("Action: check PDF file availability, PyMuPDF4LLM installation, and equation backend configuration")
        raise


if __name__ == "__main__":
    main()