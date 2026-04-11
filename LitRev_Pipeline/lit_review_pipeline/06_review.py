"""
Map-Reduce literature review orchestrator pipeline stage.

Map phase: Creates per-paper summaries using all chunks for each paper.
Reduce phase: Synthesizes all summaries into a comprehensive literature review.
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from pydantic import BaseModel, Field

# Optional dependency for Anthropic API
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from config import DATA_DIR, SUMMARIES_DIR, PARSED_DIR, ANTHROPIC_API_KEY, PIPELINE_MODEL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PaperSummary(BaseModel):
    """Pydantic model for structured paper summaries."""
    
    paper_id: str = Field(description="Unique identifier for the paper")
    title: str = Field(description="Paper title")
    authors: List[str] = Field(description="List of author names")
    year: int = Field(description="Publication year")
    objective: str = Field(description="Main research objective or question")
    methodology: str = Field(description="Research methodology and approach")
    key_equations: List[str] = Field(description="Important equations in LaTeX format")
    key_findings: List[str] = Field(description="Main research findings and results")
    limitations: str = Field(description="Study limitations and constraints")
    relevance_tags: List[str] = Field(description="Topical tags for categorization")


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


def load_paper_chunks(paper_id: str) -> List[Dict[str, Any]]:
    """
    Load all chunks for a specific paper in order.
    
    Args:
        paper_id: Paper identifier (filename stem)
        
    Returns:
        List of chunk dictionaries for the paper, ordered by section and chunk index
        
    Raises:
        FileNotFoundError: If chunks file does not exist
    """
    chunks_path = PARSED_DIR / f"{paper_id}_chunks.json"
    
    if not chunks_path.exists():
        logger.error(f"Chunks file not found: {chunks_path}")
        logger.error("Expected: per-paper chunks file from 03_chunk.py")
        logger.error("Action: run 03_chunk.py first to generate chunks")
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")
    
    try:
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        # Sort chunks by section and chunk index for consistent ordering
        sorted_chunks = sorted(
            chunks,
            key=lambda x: (
                x["metadata"].get("section", ""),
                x["metadata"].get("chunk_index", 0)
            )
        )
        
        logger.info(f"Loaded {len(sorted_chunks)} chunks for paper {paper_id}")
        return sorted_chunks
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in chunks file: {e}")
        logger.error("Expected: valid JSON format")
        logger.error("Action: check chunks file integrity or regenerate with 03_chunk.py")
        raise


def create_paper_summary_prompt(paper_metadata: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
    """
    Create a prompt for generating a paper summary from all chunks.
    
    Args:
        paper_metadata: Paper metadata from manifest
        chunks: List of all chunks for the paper
        
    Returns:
        Formatted prompt string for Claude API
    """
    title = paper_metadata.get("title", "Unknown Title")
    authors = paper_metadata.get("authors", [])
    year = paper_metadata.get("year", "Unknown Year")
    
    prompt_parts = [
        "You are a scientific literature review assistant. Please analyze the following research paper and create a structured summary.",
        "",
        f"Paper: {title}",
        f"Authors: {', '.join(authors) if authors else 'Unknown'}",
        f"Year: {year}",
        "",
        "Full Paper Content (organized by sections):",
        ""
    ]
    
    # Add all chunks organized by section
    current_section = None
    for chunk in chunks:
        section = chunk["metadata"].get("section", "Unknown Section")
        
        if section != current_section:
            current_section = section
            prompt_parts.append(f"## {section}")
            prompt_parts.append("")
        
        prompt_parts.append(chunk["text"])
        prompt_parts.append("")
    
    prompt_parts.extend([
        "Please analyze this paper and provide a structured summary in JSON format with the following fields:",
        "",
        "- paper_id: Use the filename stem as identifier",
        "- title: Paper title",
        "- authors: List of author names",
        "- year: Publication year as integer",
        "- objective: Main research objective or question (2-3 sentences)",
        "- methodology: Research methodology and approach (2-3 sentences)",
        "- key_equations: List of important equations in LaTeX format (preserve exactly as written)",
        "- key_findings: List of main research findings and results (3-5 bullet points)",
        "- limitations: Study limitations and constraints (1-2 sentences)",
        "- relevance_tags: List of 3-5 topical tags for categorization",
        "",
        "Return only the JSON object, no additional text or formatting."
    ])
    
    return "\n".join(prompt_parts)


def generate_paper_summary(paper_metadata: Dict[str, Any], chunks: List[Dict[str, Any]], 
                          anthropic_client: Anthropic) -> PaperSummary:
    """
    Generate a structured summary for a single paper using Claude API.
    
    Args:
        paper_metadata: Paper metadata from manifest
        chunks: List of all chunks for the paper
        anthropic_client: Initialized Anthropic client
        
    Returns:
        PaperSummary object with structured summary data
        
    Raises:
        Exception: If summary generation fails
    """
    paper_id = Path(paper_metadata.get("filename", "")).stem
    logger.info(f"Generating summary for paper: {paper_id}")
    
    try:
        # Create prompt
        prompt = create_paper_summary_prompt(paper_metadata, chunks)
        
        # Call Claude API
        response = anthropic_client.messages.create(
            model=PIPELINE_MODEL,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        response_text = response.content[0].text.strip()
        response_text = response_text.strip()
        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\s*\n?", "", response_text)
            response_text = re.sub(r"\n?```\s*$", "", response_text)
        # Parse JSON response
        try:
            summary_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response if wrapped in markdown
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
            
            summary_data = json.loads(json_text)
        
        # Ensure paper_id is set correctly
        summary_data["paper_id"] = paper_id
        
        # Create and validate PaperSummary object
        paper_summary = PaperSummary(**summary_data)
        
        logger.info(f"Successfully generated summary for paper: {paper_id}")
        return paper_summary
        
    except Exception as e:
        logger.error(f"Failed to generate summary for paper {paper_id}: {e}")
        logger.error("Expected: successful Claude API call and JSON parsing")
        logger.error("Action: check API key, model availability, and response format")
        raise


def save_paper_summary(paper_summary: PaperSummary) -> None:
    """
    Save a paper summary to JSON file using Pydantic's model_dump_json method.
    
    Args:
        paper_summary: PaperSummary object to save
        
    Raises:
        Exception: If file saving fails
    """
    # Ensure summaries directory exists
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save summary using Pydantic's model_dump_json
    summary_path = SUMMARIES_DIR / f"{paper_summary.paper_id}_summary.json"
    
    try:
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(paper_summary.model_dump_json(indent=2))
        
        logger.info(f"Saved summary to {summary_path.name}")
        
    except Exception as e:
        logger.error(f"Failed to save summary for {paper_summary.paper_id}: {e}")
        logger.error("Expected: successful file writing")
        logger.error("Action: check directory permissions and disk space")
        raise


def map_phase(manifest_entries: List[Dict[str, Any]], anthropic_client: Anthropic) -> List[PaperSummary]:
    """
    Map phase: Generate summaries for all papers.
    
    Args:
        manifest_entries: List of manifest entries containing paper metadata
        anthropic_client: Initialized Anthropic client
        
    Returns:
        List of PaperSummary objects for all processed papers
    """
    logger.info(f"Starting map phase: processing {len(manifest_entries)} papers")
    
    paper_summaries = []
    successful_count = 0
    failed_count = 0
    
    for entry in manifest_entries:
        filename = entry.get("filename", "")
        if not filename:
            logger.warning("Manifest entry missing filename - skipping")
            failed_count += 1
            continue
        
        paper_id = Path(filename).stem
        
        try:
            # Load paper chunks
            chunks = load_paper_chunks(paper_id)
            
            if not chunks:
                logger.warning(f"No chunks found for paper {paper_id} - skipping")
                failed_count += 1
                continue
            
            # Generate summary
            paper_summary = generate_paper_summary(entry, chunks, anthropic_client)
            
            # Save summary
            save_paper_summary(paper_summary)
            
            paper_summaries.append(paper_summary)
            successful_count += 1
            
        except Exception as e:
            logger.error(f"Failed to process paper {paper_id}: {e}")
            logger.error("Continuing with next paper")
            failed_count += 1
    
    logger.info(f"Map phase completed: {successful_count} successful, {failed_count} failed")
    return paper_summaries


def load_all_summaries() -> List[PaperSummary]:
    """
    Load all paper summaries from the summaries directory.
    
    Returns:
        List of PaperSummary objects loaded from JSON files
        
    Raises:
        Exception: If loading fails
    """
    if not SUMMARIES_DIR.exists():
        logger.error(f"Summaries directory not found: {SUMMARIES_DIR}")
        logger.error("Expected: summaries directory with JSON files from map phase")
        logger.error("Action: run map phase first to generate summaries")
        raise FileNotFoundError(f"Summaries directory not found: {SUMMARIES_DIR}")
    
    summary_files = list(SUMMARIES_DIR.glob("*_summary.json"))
    
    if not summary_files:
        logger.error("No summary files found in summaries directory")
        logger.error("Expected: JSON summary files from map phase")
        logger.error("Action: run map phase first to generate summaries")
        raise FileNotFoundError("No summary files found")
    
    logger.info(f"Loading {len(summary_files)} summary files")
    
    summaries = []
    for summary_file in summary_files:
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            
            paper_summary = PaperSummary(**summary_data)
            summaries.append(paper_summary)
            
        except Exception as e:
            logger.error(f"Failed to load summary from {summary_file.name}: {e}")
            logger.error("Continuing with other summaries")
    
    logger.info(f"Successfully loaded {len(summaries)} paper summaries")
    return summaries


def create_synthesis_prompt(paper_summaries: List[PaperSummary]) -> str:
    """
    Create a prompt for synthesizing all paper summaries into a literature review.
    
    Args:
        paper_summaries: List of PaperSummary objects
        
    Returns:
        Formatted prompt string for Claude API
    """
    prompt_parts = [
        "You are a scientific literature review expert. Please synthesize the following paper summaries into a comprehensive literature review.",
        "",
        "Paper Summaries:",
        ""
    ]
    
    # Add all paper summaries
    for i, summary in enumerate(paper_summaries, 1):
        prompt_parts.extend([
            f"## Paper {i}: {summary.title}",
            f"**Authors:** {', '.join(summary.authors)}",
            f"**Year:** {summary.year}",
            f"**Objective:** {summary.objective}",
            f"**Methodology:** {summary.methodology}",
            f"**Key Equations:** {', '.join(summary.key_equations) if summary.key_equations else 'None'}",
            f"**Key Findings:**",
        ])
        
        for finding in summary.key_findings:
            prompt_parts.append(f"- {finding}")
        
        prompt_parts.extend([
            f"**Limitations:** {summary.limitations}",
            f"**Tags:** {', '.join(summary.relevance_tags)}",
            ""
        ])
    
    prompt_parts.extend([
        "Please create a comprehensive literature review with the following sections:",
        "",
        "1. **Introduction** - Brief overview of the research domain and scope",
        "2. **Thematic Grouping** - Group papers by research themes and topics",
        "3. **Methodological Comparison** - Compare and contrast research methodologies",
        "4. **Mathematical Models and Equations** - Analyze key equations and models used",
        "5. **Consensus and Contradictions** - Identify areas of agreement and disagreement",
        "6. **Research Gaps** - Highlight identified gaps in current knowledge",
        "7. **Future Work** - Suggest directions for future research",
        "8. **Conclusion** - Summarize key insights and implications",
        "",
        "Requirements:",
        "- Use proper Markdown formatting with section headings",
        "- Preserve LaTeX equations exactly as they appear in the summaries",
        "- Cite papers using author-year format when referencing specific findings",
        "- Provide a balanced and objective analysis",
        "- Focus on scientific rigor and evidence-based conclusions",
        "",
        "Literature Review:"
    ])
    
    return "\n".join(prompt_parts)


def generate_literature_review(paper_summaries: List[PaperSummary], anthropic_client: Anthropic) -> str:
    """
    Generate a comprehensive literature review from all paper summaries.
    
    Args:
        paper_summaries: List of PaperSummary objects
        anthropic_client: Initialized Anthropic client
        
    Returns:
        Generated literature review as Markdown text
        
    Raises:
        Exception: If review generation fails
    """
    logger.info(f"Generating literature review from {len(paper_summaries)} paper summaries")
    
    try:
        # Create synthesis prompt
        prompt = create_synthesis_prompt(paper_summaries)
        
        # Call Claude API with larger token limit for comprehensive review
        response = anthropic_client.messages.create(
            model=PIPELINE_MODEL,
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        literature_review = response.content[0].text.strip()
        
        logger.info("Successfully generated literature review")
        return literature_review
        
    except Exception as e:
        logger.error(f"Failed to generate literature review: {e}")
        logger.error("Expected: successful Claude API call for synthesis")
        logger.error("Action: check API key, model availability, and prompt length")
        raise


def save_literature_review(literature_review: str) -> None:
    """
    Save the literature review to a Markdown file.
    
    Args:
        literature_review: Generated literature review text
        
    Raises:
        Exception: If file saving fails
    """
    # Ensure summaries directory exists
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    
    review_path = SUMMARIES_DIR / "literature_review.md"
    
    try:
        with open(review_path, 'w', encoding='utf-8') as f:
            f.write(literature_review)
        
        logger.info(f"Saved literature review to {review_path}")
        
    except Exception as e:
        logger.error(f"Failed to save literature review: {e}")
        logger.error("Expected: successful file writing")
        logger.error("Action: check directory permissions and disk space")
        raise


def reduce_phase(anthropic_client: Anthropic) -> None:
    """
    Reduce phase: Synthesize all paper summaries into a comprehensive literature review.
    
    Args:
        anthropic_client: Initialized Anthropic client
    """
    logger.info("Starting reduce phase: synthesizing literature review")
    
    try:
        # Load all paper summaries
        paper_summaries = load_all_summaries()
        
        if not paper_summaries:
            logger.error("No paper summaries available for synthesis")
            logger.error("Expected: paper summaries from map phase")
            logger.error("Action: run map phase first to generate summaries")
            raise ValueError("No paper summaries available")
        
        # Generate literature review
        literature_review = generate_literature_review(paper_summaries, anthropic_client)
        
        # Save literature review
        save_literature_review(literature_review)
        
        logger.info("Reduce phase completed successfully")
        
    except Exception as e:
        logger.error(f"Reduce phase failed: {e}")
        logger.error("Expected: successful literature review synthesis")
        logger.error("Action: check summary availability and API connectivity")
        raise


def main() -> None:
    """Main pipeline execution function."""
    logger.info("Starting Map-Reduce literature review orchestrator")
    
    # Validate Anthropic client availability
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set")
        logger.error("Expected: valid Anthropic API key")
        logger.error("Action: set ANTHROPIC_API_KEY environment variable")
        raise ValueError("ANTHROPIC_API_KEY not set")
    
    if not Anthropic:
        logger.error("anthropic package not installed")
        logger.error("Expected: anthropic package to be available")
        logger.error("Action: install anthropic package")
        raise ImportError("anthropic package not installed")
    
    try:
        # Initialize Anthropic client
        anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
        logger.info("Successfully initialized Anthropic client")
        
        # Load manifest
        manifest_entries = load_manifest()
        
        if not manifest_entries:
            logger.warning("No entries in manifest - pipeline completed with no processing")
            return
        
        # Map phase: Generate per-paper summaries
        paper_summaries = map_phase(manifest_entries, anthropic_client)
        
        if not paper_summaries:
            logger.error("No paper summaries generated in map phase")
            logger.error("Expected: at least one successful paper summary")
            logger.error("Action: check paper chunks availability and API connectivity")
            raise ValueError("No paper summaries generated")
        
        # Reduce phase: Synthesize literature review
        reduce_phase(anthropic_client)
        
        logger.info("Map-Reduce literature review orchestrator completed successfully")
        
        # Log summary statistics
        logger.info(f"Pipeline statistics:")
        logger.info(f"  Papers processed: {len(paper_summaries)}")
        logger.info(f"  Summaries saved: data/summaries/*_summary.json")
        logger.info(f"  Literature review: data/summaries/literature_review.md")
        
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        logger.error("Expected: successful map-reduce literature review generation")
        logger.error("Action: check all dependencies, API keys, and previous pipeline stages")
        raise


if __name__ == "__main__":
    main()