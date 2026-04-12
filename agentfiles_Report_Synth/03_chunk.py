"""
Section-aware chunking pipeline stage with equation preservation.

Loads merged Markdown files and creates section-aware chunks that preserve LaTeX equations.
Outputs per-paper chunk files and aggregated chunks with metadata.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from config import DATA_DIR, PARSED_DIR, MAX_CHUNK_SIZE, CHUNK_OVERLAP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chunking configuration
MIN_CHUNK_TOKENS = 100
MAX_CHUNK_TOKENS = MAX_CHUNK_SIZE


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


def count_tokens(text: str) -> int:
    """
    Count tokens in text using whitespace splitting heuristic.
    
    Args:
        text: Text to count tokens for
        
    Returns:
        Number of tokens (words)
    """
    return len(text.split())


def detect_section_headers(text: str) -> List[Tuple[int, str, str]]:
    """
    Detect section headers in Markdown text using regex patterns.
    
    Args:
        text: Markdown text to analyze
        
    Returns:
        List of tuples (line_number, header_text, section_name)
    """
    # Section header patterns for scientific papers
    section_patterns = [
        # Standard scientific sections
        r'(?i)^#+\s*(abstract)\s*$',
        r'(?i)^#+\s*(introduction)\s*$',
        r'(?i)^#+\s*(methods?|methodology)\s*$',
        r'(?i)^#+\s*(materials?\s+and\s+methods?)\s*$',
        r'(?i)^#+\s*(experimental\s+setup)\s*$',
        r'(?i)^#+\s*(results?)\s*$',
        r'(?i)^#+\s*(discussion)\s*$',
        r'(?i)^#+\s*(results?\s+and\s+discussion)\s*$',
        r'(?i)^#+\s*(conclusions?)\s*$',
        r'(?i)^#+\s*(references?)\s*$',
        r'(?i)^#+\s*(bibliography)\s*$',
        r'(?i)^#+\s*(acknowledgments?)\s*$',
        r'(?i)^#+\s*(appendix|appendices)\s*$',
        
        # Numbered sections (e.g., "2.1 Methodology", "3 Results")
        r'^#+\s*(\d+(?:\.\d+)*\s+[A-Za-z][^#\n]*)\s*$',
        
        # Generic markdown headers
        r'^#+\s*([A-Za-z][^#\n]*)\s*$'
    ]
    
    headers = []
    lines = text.split('\n')
    
    for line_num, line in enumerate(lines):
        for pattern in section_patterns:
            match = re.match(pattern, line.strip())
            if match:
                header_text = line.strip()
                section_name = match.group(1).strip()
                headers.append((line_num, header_text, section_name))
                break  # Use first matching pattern
    
    logger.debug(f"Detected {len(headers)} section headers")
    return headers


def find_equation_boundaries(text: str) -> List[Tuple[int, int]]:
    """
    Find all equation boundaries in text to avoid splitting equations.
    
    Args:
        text: Text to analyze for equations
        
    Returns:
        List of tuples (start_pos, end_pos) for equation boundaries
    """
    equation_boundaries = []
    
    # Find display equations ($$...$$)
    display_pattern = r'\$\$[^$]*\$\$'
    for match in re.finditer(display_pattern, text, re.DOTALL):
        equation_boundaries.append((match.start(), match.end()))
    
    # Find inline equations ($...$) that don't overlap with display equations
    inline_pattern = r'(?<!\$)\$[^$\n]+\$(?!\$)'
    for match in re.finditer(inline_pattern, text):
        start, end = match.start(), match.end()
        
        # Check if this inline equation overlaps with any display equation
        overlaps = False
        for disp_start, disp_end in equation_boundaries:
            if not (end <= disp_start or start >= disp_end):
                overlaps = True
                break
        
        if not overlaps:
            equation_boundaries.append((start, end))
    
    # Sort by start position
    equation_boundaries.sort(key=lambda x: x[0])
    
    logger.debug(f"Found {len(equation_boundaries)} equation boundaries")
    return equation_boundaries


def is_safe_split_position(text: str, position: int, equation_boundaries: List[Tuple[int, int]]) -> bool:
    """
    Check if a position is safe for splitting (not inside an equation).
    
    Args:
        text: Full text being analyzed
        position: Character position to check
        equation_boundaries: List of equation boundary tuples
        
    Returns:
        True if position is safe for splitting, False otherwise
    """
    for start, end in equation_boundaries:
        if start <= position <= end:
            return False
    return True


def calculate_equation_ratio(text: str) -> float:
    """
    Calculate the ratio of equation content to total content in text.
    
    Args:
        text: Text to analyze
        
    Returns:
        Ratio of equation tokens to total tokens (0.0 to 1.0)
    """
    total_tokens = count_tokens(text)
    if total_tokens == 0:
        return 0.0
    
    # Extract equation content
    equation_content = ""
    
    # Display equations
    display_matches = re.findall(r'\$\$([^$]*)\$\$', text, re.DOTALL)
    for match in display_matches:
        equation_content += match + " "
    
    # Inline equations
    inline_matches = re.findall(r'(?<!\$)\$([^$\n]+)\$(?!\$)', text)
    for match in inline_matches:
        equation_content += match + " "
    
    equation_tokens = count_tokens(equation_content)
    return equation_tokens / total_tokens


def find_preceding_paragraph(text: str, chunk_start: int) -> str:
    """
    Find the preceding prose paragraph for a chunk with high equation content.
    
    Args:
        text: Full text
        chunk_start: Start position of the chunk
        
    Returns:
        Preceding paragraph text or empty string if none found
    """
    if chunk_start == 0:
        return ""
    
    # Look backwards for paragraph breaks
    preceding_text = text[:chunk_start]
    paragraphs = preceding_text.split('\n\n')
    
    if len(paragraphs) < 2:
        return ""
    
    # Get the last complete paragraph
    last_paragraph = paragraphs[-2].strip()
    
    # Filter out headers and very short paragraphs
    if (len(last_paragraph) < 50 or 
        last_paragraph.startswith('#') or
        calculate_equation_ratio(last_paragraph) > 0.5):
        return ""
    
    return last_paragraph


def split_at_paragraph_breaks(text: str, max_tokens: int, equation_boundaries: List[Tuple[int, int]]) -> List[str]:
    """
    Split text at paragraph breaks (double newlines) while respecting equation boundaries.
    
    Args:
        text: Text to split
        max_tokens: Maximum tokens per chunk
        equation_boundaries: List of equation boundary tuples
        
    Returns:
        List of text chunks
    """
    chunks = []
    current_chunk = ""
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        # Calculate tokens if we add this paragraph
        test_chunk = current_chunk + '\n\n' + paragraph if current_chunk else paragraph
        test_tokens = count_tokens(test_chunk)
        
        if test_tokens <= max_tokens:
            # Add paragraph to current chunk
            current_chunk = test_chunk
        else:
            # Current chunk is full, start new chunk
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = paragraph
    
    # Add final chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def create_section_chunks(text: str, section_name: str, paper_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Create chunks from a section of text with equation preservation.
    
    Args:
        text: Section text to chunk
        section_name: Name of the section
        paper_metadata: Metadata for the paper
        
    Returns:
        List of chunk dictionaries with metadata
    """
    chunks = []
    
    if not text.strip():
        return chunks
    
    # Find equation boundaries
    equation_boundaries = find_equation_boundaries(text)
    
    # Check if section fits in one chunk
    total_tokens = count_tokens(text)
    if total_tokens <= MAX_CHUNK_TOKENS:
        # Single chunk for this section
        chunk_metadata = create_chunk_metadata(
            text, paper_metadata, section_name, 0, equation_boundaries
        )
        chunks.append({
            "text": text,
            "metadata": chunk_metadata
        })
        return chunks
    
    # Split section at paragraph breaks
    section_chunks = split_at_paragraph_breaks(text, MAX_CHUNK_TOKENS, equation_boundaries)
    
    for chunk_index, chunk_text in enumerate(section_chunks):
        # Check equation ratio
        equation_ratio = calculate_equation_ratio(chunk_text)
        
        # If chunk is >60% equations, prepend preceding paragraph
        if equation_ratio > 0.6 and chunk_index > 0:
            # Find preceding paragraph from previous chunk
            if chunk_index > 0:
                preceding_chunk = section_chunks[chunk_index - 1]
                preceding_paragraphs = preceding_chunk.split('\n\n')
                if preceding_paragraphs:
                    preceding_paragraph = preceding_paragraphs[-1].strip()
                    if preceding_paragraph and not preceding_paragraph.startswith('#'):
                        chunk_text = preceding_paragraph + '\n\n' + chunk_text
        
        # Create chunk metadata
        chunk_boundaries = find_equation_boundaries(chunk_text)
        chunk_metadata = create_chunk_metadata(
            chunk_text, paper_metadata, section_name, chunk_index, chunk_boundaries
        )
        
        chunks.append({
            "text": chunk_text,
            "metadata": chunk_metadata
        })
    
    return chunks


def create_chunk_metadata(text: str, paper_metadata: Dict[str, Any], section_name: str, 
                         chunk_index: int, equation_boundaries: List[Tuple[int, int]]) -> Dict[str, Any]:
    """
    Create metadata dictionary for a chunk.
    
    Args:
        text: Chunk text
        paper_metadata: Paper metadata from manifest
        section_name: Name of the section
        chunk_index: Index of chunk within section
        equation_boundaries: Equation boundaries in the chunk
        
    Returns:
        Metadata dictionary
    """
    # Extract paper ID from filename
    filename = paper_metadata.get("filename", "")
    paper_id = Path(filename).stem if filename else "unknown"
    
    # Check for equations
    has_equations = len(equation_boundaries) > 0
    
    # Check for figures (simple heuristic)
    has_figures = bool(re.search(r'(?i)\bfig(?:ure)?\s*\.?\s*\d+', text))
    
    # Extract page numbers (simple heuristic from page markers)
    page_numbers = []
    page_matches = re.findall(r'(?i)page\s+(\d+)', text)
    if page_matches:
        page_numbers = [int(p) for p in page_matches]
    
    return {
        "paper_id": paper_id,
        "title": paper_metadata.get("title", ""),
        "authors": paper_metadata.get("authors", []),
        "year": paper_metadata.get("year"),
        "journal": paper_metadata.get("journal", ""),
        "doi": paper_metadata.get("doi", ""),
        "section": section_name,
        "chunk_index": chunk_index,
        "has_equations": has_equations,
        "has_figures": has_figures,
        "page_numbers": page_numbers
    }


def chunk_document(markdown_content: str, paper_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Chunk a document into section-aware chunks with equation preservation.
    
    Args:
        markdown_content: Full Markdown content of the document
        paper_metadata: Paper metadata from manifest
        
    Returns:
        List of chunk dictionaries
    """
    logger.info(f"Chunking document: {paper_metadata.get('title', 'Unknown')}")
    
    # Detect section headers
    headers = detect_section_headers(markdown_content)
    
    if not headers:
        logger.warning("No section headers detected, treating as single section")
        # Treat entire document as one section
        chunks = create_section_chunks(markdown_content, "Document", paper_metadata)
        logger.info(f"Created {len(chunks)} chunks from single section")
        return chunks
    
    # Split document by sections
    lines = markdown_content.split('\n')
    all_chunks = []
    
    for i, (line_num, header_text, section_name) in enumerate(headers):
        # Determine section boundaries
        section_start = line_num
        if i + 1 < len(headers):
            section_end = headers[i + 1][0]
        else:
            section_end = len(lines)
        
        # Extract section content
        section_lines = lines[section_start:section_end]
        section_content = '\n'.join(section_lines).strip()
        
        if not section_content:
            continue
        
        # Create chunks for this section
        section_chunks = create_section_chunks(section_content, section_name, paper_metadata)
        all_chunks.extend(section_chunks)
        
        logger.debug(f"Section '{section_name}': {len(section_chunks)} chunks")
    
    logger.info(f"Created {len(all_chunks)} total chunks from {len(headers)} sections")
    return all_chunks


def process_single_document(paper_metadata: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Process a single document for chunking.
    
    Args:
        paper_metadata: Paper metadata from manifest
        
    Returns:
        List of chunk dictionaries or None if processing fails
    """
    filename = paper_metadata.get("filename", "")
    if not filename:
        logger.warning("Paper metadata missing filename - skipping")
        return None
    
    # Construct paths
    filename_stem = Path(filename).stem
    merged_path = PARSED_DIR / f"{filename_stem}_merged.md"
    
    if not merged_path.exists():
        logger.error(f"Merged Markdown file not found: {merged_path}")
        logger.error("Expected: merged Markdown file from 02_parse.py")
        logger.error("Action: run 02_parse.py first to generate merged files")
        return None
    
    try:
        # Load merged Markdown content
        with open(merged_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Create chunks
        chunks = chunk_document(markdown_content, paper_metadata)
        
        # Save per-paper chunks file
        chunks_path = PARSED_DIR / f"{filename_stem}_chunks.json"
        with open(chunks_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(chunks)} chunks to {chunks_path.name}")
        return chunks
        
    except Exception as e:
        logger.error(f"Failed to process {filename}: {e}")
        return None


def process_all_documents(manifest_entries: List[Dict[str, Any]]) -> None:
    """
    Process all documents from the manifest for chunking.
    
    Args:
        manifest_entries: List of manifest entries containing paper metadata
    """
    logger.info(f"Processing {len(manifest_entries)} documents for chunking")
    
    all_chunks = []
    successful_count = 0
    failed_count = 0
    
    for entry in manifest_entries:
        chunks = process_single_document(entry)
        if chunks is not None:
            all_chunks.extend(chunks)
            successful_count += 1
        else:
            logger.error("Continuing with next document")
            failed_count += 1
    
    # Save aggregated chunks file
    aggregated_path = PARSED_DIR / "all_chunks.json"
    try:
        with open(aggregated_path, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(all_chunks)} total chunks to {aggregated_path.name}")
        
    except Exception as e:
        logger.error(f"Failed to save aggregated chunks: {e}")
        logger.error("Expected: writable parsed directory")
        logger.error("Action: check directory permissions and disk space")
        raise
    
    logger.info(f"Chunking pipeline completed: {successful_count} successful, {failed_count} failed")
    
    # Log statistics
    if all_chunks:
        chunk_sizes = [count_tokens(chunk["text"]) for chunk in all_chunks]
        avg_size = sum(chunk_sizes) / len(chunk_sizes)
        min_size = min(chunk_sizes)
        max_size = max(chunk_sizes)
        
        equation_chunks = sum(1 for chunk in all_chunks if chunk["metadata"]["has_equations"])
        figure_chunks = sum(1 for chunk in all_chunks if chunk["metadata"]["has_figures"])
        
        logger.info(f"Chunk statistics:")
        logger.info(f"  Average size: {avg_size:.1f} tokens")
        logger.info(f"  Size range: {min_size} - {max_size} tokens")
        logger.info(f"  Chunks with equations: {equation_chunks}/{len(all_chunks)}")
        logger.info(f"  Chunks with figures: {figure_chunks}/{len(all_chunks)}")


def main() -> None:
    """Main pipeline execution function."""
    logger.info("Starting section-aware chunking pipeline")
    
    try:
        # Load manifest
        manifest_entries = load_manifest()
        
        if not manifest_entries:
            logger.warning("No entries in manifest - pipeline completed with no processing")
            return
        
        # Process all documents
        process_all_documents(manifest_entries)
        
        logger.info("Section-aware chunking pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        logger.error("Expected: successful chunking of all merged Markdown files")
        logger.error("Action: check merged Markdown file availability and chunking configuration")
        raise


if __name__ == "__main__":
    main()