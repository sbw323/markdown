"""
PDF intake and metadata extraction pipeline stage.

Scans data/pdfs/ for PDF files and extracts metadata using GROBID with Claude vision fallback.
Outputs data/manifest.json containing metadata for all processed papers.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

from config import PDFS_DIR, DATA_DIR
from utils.metadata import MetadataExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def scan_pdfs_directory() -> List[Path]:
    """
    Scan the PDFs directory for all PDF files.
    
    Returns:
        List of Path objects for all PDF files found
    """
    logger.info(f"Scanning for PDFs in {PDFS_DIR}")
    
    if not PDFS_DIR.exists():
        logger.error(f"PDFs directory does not exist: {PDFS_DIR}")
        logger.error("Please create the directory and add PDF files to process")
        return []
    
    pdf_files = list(PDFS_DIR.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files")
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {PDFS_DIR}")
        logger.warning("Please add PDF files to the directory and run again")
    
    return pdf_files


def process_pdfs(pdf_files: List[Path]) -> List[Dict[str, Any]]:
    """
    Process all PDF files to extract metadata.
    
    Args:
        pdf_files: List of PDF file paths to process
        
    Returns:
        List of metadata dictionaries for all processed papers
    """
    logger.info(f"Processing {len(pdf_files)} PDF files for metadata extraction")
    
    extractor = MetadataExtractor()
    manifest_entries = []
    
    for pdf_path in pdf_files:
        try:
            logger.info(f"Processing {pdf_path.name}")
            metadata = extractor.extract_metadata(pdf_path)
            manifest_entries.append(metadata)
            logger.info(f"Successfully processed {pdf_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to process {pdf_path.name}: {e}")
            logger.error("Continuing with next PDF file")
            
            # Add minimal entry for failed processing
            failed_metadata = {
                "filename": pdf_path.name,
                "title": "",
                "authors": [],
                "year": None,
                "journal": "",
                "doi": "",
                "abstract": ""
            }
            manifest_entries.append(failed_metadata)
    
    logger.info(f"Completed processing {len(manifest_entries)} PDF files")
    return manifest_entries


def save_manifest(manifest_entries: List[Dict[str, Any]]) -> None:
    """
    Save the manifest entries to data/manifest.json.
    
    Args:
        manifest_entries: List of metadata dictionaries to save
    """
    manifest_path = DATA_DIR / "manifest.json"
    
    try:
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save manifest
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_entries, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved manifest with {len(manifest_entries)} entries to {manifest_path}")
        
        # Log summary statistics
        successful_extractions = sum(1 for entry in manifest_entries if entry.get("title"))
        logger.info(f"Successfully extracted metadata for {successful_extractions}/{len(manifest_entries)} papers")
        
    except Exception as e:
        logger.error(f"Failed to save manifest to {manifest_path}: {e}")
        logger.error("Expected: writable data directory")
        logger.error("Action: check directory permissions and disk space")
        raise


def main() -> None:
    """Main pipeline execution function."""
    logger.info("Starting PDF intake and metadata extraction pipeline")
    
    try:
        # Scan for PDF files
        pdf_files = scan_pdfs_directory()
        if not pdf_files:
            logger.warning("No PDF files to process - pipeline completed with empty results")
            # Still create empty manifest
            save_manifest([])
            return
        
        # Process PDFs for metadata
        manifest_entries = process_pdfs(pdf_files)
        
        # Save manifest
        save_manifest(manifest_entries)
        
        logger.info("PDF intake and metadata extraction pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        logger.error("Expected: successful metadata extraction and manifest creation")
        logger.error("Action: check GROBID service availability and API credentials")
        raise


if __name__ == "__main__":
    main()