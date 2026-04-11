"""
End-to-end integration test for the scientific literature review pipeline.

Creates a synthetic PDF and runs the complete pipeline from 01_ingest.py through 06_review.py,
validating outputs at each stage and reporting pass/fail with timing information.
"""

import json
import logging
import os
import pickle
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple

import chromadb

# Try to import reportlab, fall back to fpdf2 if not available
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Try fpdf2 as fallback
try:
    from fpdf import FPDF
    FPDF2_AVAILABLE = True
except ImportError:
    FPDF2_AVAILABLE = False

from config import (
    DATA_DIR, PDFS_DIR, PARSED_DIR, SUMMARIES_DIR, VECTORSTORE_DIR,
    WORKSPACE_ROOT
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineTestResult:
    """Container for pipeline test results."""
    
    def __init__(self, phase_name: str) -> None:
        """Initialize test result."""
        self.phase_name = phase_name
        self.passed = False
        self.elapsed_time = 0.0
        self.error_message = ""
        self.exit_code = None


def create_synthetic_pdf_reportlab() -> Path:
    """
    Create a synthetic PDF using reportlab.
    
    Returns:
        Path to the created synthetic PDF file
    """
    pdf_path = PDFS_DIR / "test_paper.pdf"
    
    # Create PDF document
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=1  # Center alignment
    )
    story.append(Paragraph("A Novel Approach to Quantum Computing Optimization", title_style))
    story.append(Spacer(1, 12))
    
    # Authors
    author_style = ParagraphStyle(
        'Authors',
        parent=styles['Normal'],
        fontSize=12,
        alignment=1,
        spaceAfter=20
    )
    story.append(Paragraph("John Smith, Jane Doe, Robert Johnson", author_style))
    story.append(Spacer(1, 20))
    
    # Abstract section
    story.append(Paragraph("Abstract", styles['Heading2']))
    abstract_text = """
    This paper presents a novel optimization algorithm for quantum computing systems.
    We demonstrate significant improvements in computational efficiency through the use
    of advanced mathematical techniques. Our approach shows a 40% reduction in
    processing time compared to existing methods.
    """
    story.append(Paragraph(abstract_text, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Introduction section
    story.append(Paragraph("1. Introduction", styles['Heading2']))
    intro_text = """
    Quantum computing represents a paradigm shift in computational capabilities.
    Traditional algorithms face limitations when dealing with complex optimization
    problems. This research addresses these challenges through innovative mathematical
    modeling and algorithmic design.
    """
    story.append(Paragraph(intro_text, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Methods section with equation placeholder
    story.append(Paragraph("2. Methods", styles['Heading2']))
    methods_text = """
    Our optimization algorithm is based on the following mathematical framework.
    The core equation governing our approach is shown below:
    """
    story.append(Paragraph(methods_text, styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Add equation as text (will be detected by equation handler)
    equation_text = "[EQUATION] $$H = \\sum_{i=1}^{n} \\alpha_i |\\psi_i\\rangle\\langle\\psi_i| + \\beta \\sum_{i,j} J_{ij} \\sigma_i^z \\sigma_j^z$$"
    equation_style = ParagraphStyle(
        'Equation',
        parent=styles['Normal'],
        fontSize=12,
        alignment=1,
        leftIndent=20,
        rightIndent=20
    )
    story.append(Paragraph(equation_text, equation_style))
    story.append(Spacer(1, 20))
    
    # Results section
    story.append(Paragraph("3. Results", styles['Heading2']))
    results_text = """
    Our experimental results demonstrate the effectiveness of the proposed algorithm.
    Figure 1 shows the performance comparison between our method and existing approaches.
    The optimization converges significantly faster while maintaining solution quality.
    """
    story.append(Paragraph(results_text, styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Add figure placeholder
    figure_text = "Figure 1: Performance comparison showing 40% improvement in convergence time."
    figure_style = ParagraphStyle(
        'Figure',
        parent=styles['Normal'],
        fontSize=10,
        alignment=1,
        leftIndent=20,
        rightIndent=20,
        spaceBefore=10,
        spaceAfter=10
    )
    story.append(Paragraph(figure_text, figure_style))
    story.append(Spacer(1, 20))
    
    # Discussion section
    story.append(Paragraph("4. Discussion", styles['Heading2']))
    discussion_text = """
    The results indicate that our quantum optimization algorithm provides substantial
    improvements over classical methods. The mathematical formulation allows for
    efficient implementation on current quantum hardware platforms. Future work
    will explore applications to larger problem instances.
    """
    story.append(Paragraph(discussion_text, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Conclusion section
    story.append(Paragraph("5. Conclusion", styles['Heading2']))
    conclusion_text = """
    We have presented a novel quantum computing optimization algorithm that demonstrates
    significant performance improvements. The approach is mathematically sound and
    practically implementable. This work opens new avenues for quantum algorithm
    development and optimization research.
    """
    story.append(Paragraph(conclusion_text, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # References section
    story.append(Paragraph("References", styles['Heading2']))
    references_text = """
    [1] Smith, J. et al. (2023). Quantum Algorithm Foundations. Nature Quantum, 15(3), 123-145.<br/>
    [2] Doe, J. and Johnson, R. (2022). Optimization in Quantum Systems. Physical Review A, 98(4), 042301.<br/>
    [3] Brown, A. (2021). Mathematical Methods for Quantum Computing. Cambridge University Press.
    """
    story.append(Paragraph(references_text, styles['Normal']))
    
    # Build PDF
    doc.build(story)
    
    return pdf_path


def create_synthetic_pdf_fpdf2() -> Path:
    """
    Create a synthetic PDF using fpdf2.
    
    Returns:
        Path to the created synthetic PDF file
    """
    pdf_path = PDFS_DIR / "test_paper.pdf"
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    
    # Title
    pdf.cell(0, 10, 'A Novel Approach to Quantum Computing Optimization', 0, 1, 'C')
    pdf.ln(5)
    
    # Authors
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, 'John Smith, Jane Doe, Robert Johnson', 0, 1, 'C')
    pdf.ln(10)
    
    # Abstract
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Abstract', 0, 1)
    pdf.set_font('Arial', '', 11)
    abstract_text = """This paper presents a novel optimization algorithm for quantum computing systems.
We demonstrate significant improvements in computational efficiency through the use
of advanced mathematical techniques. Our approach shows a 40% reduction in
processing time compared to existing methods."""
    
    # Split text into lines for multi_cell
    pdf.multi_cell(0, 5, abstract_text)
    pdf.ln(5)
    
    # Introduction
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '1. Introduction', 0, 1)
    pdf.set_font('Arial', '', 11)
    intro_text = """Quantum computing represents a paradigm shift in computational capabilities.
Traditional algorithms face limitations when dealing with complex optimization
problems. This research addresses these challenges through innovative mathematical
modeling and algorithmic design."""
    pdf.multi_cell(0, 5, intro_text)
    pdf.ln(5)
    
    # Methods
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '2. Methods', 0, 1)
    pdf.set_font('Arial', '', 11)
    methods_text = """Our optimization algorithm is based on the following mathematical framework.
The core equation governing our approach is shown below:"""
    pdf.multi_cell(0, 5, methods_text)
    pdf.ln(3)
    
    # Equation placeholder
    pdf.set_font('Arial', 'I', 10)
    equation_text = "[EQUATION] H = sum(alpha_i |psi_i><psi_i|) + beta * sum(J_ij * sigma_i^z * sigma_j^z)"
    pdf.multi_cell(0, 5, equation_text, 0, 'C')
    pdf.ln(5)
    
    # Results
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '3. Results', 0, 1)
    pdf.set_font('Arial', '', 11)
    results_text = """Our experimental results demonstrate the effectiveness of the proposed algorithm.
Figure 1 shows the performance comparison between our method and existing approaches.
The optimization converges significantly faster while maintaining solution quality."""
    pdf.multi_cell(0, 5, results_text)
    pdf.ln(3)
    
    # Figure placeholder
    pdf.set_font('Arial', 'I', 10)
    pdf.cell(0, 5, 'Figure 1: Performance comparison showing 40% improvement in convergence time.', 0, 1, 'C')
    pdf.ln(5)
    
    # Discussion
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '4. Discussion', 0, 1)
    pdf.set_font('Arial', '', 11)
    discussion_text = """The results indicate that our quantum optimization algorithm provides substantial
improvements over classical methods. The mathematical formulation allows for
efficient implementation on current quantum hardware platforms. Future work
will explore applications to larger problem instances."""
    pdf.multi_cell(0, 5, discussion_text)
    pdf.ln(5)
    
    # Conclusion
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '5. Conclusion', 0, 1)
    pdf.set_font('Arial', '', 11)
    conclusion_text = """We have presented a novel quantum computing optimization algorithm that demonstrates
significant performance improvements. The approach is mathematically sound and
practically implementable. This work opens new avenues for quantum algorithm
development and optimization research."""
    pdf.multi_cell(0, 5, conclusion_text)
    pdf.ln(5)
    
    # References
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'References', 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 5, '[1] Smith, J. et al. (2023). Quantum Algorithm Foundations. Nature Quantum, 15(3), 123-145.')
    pdf.multi_cell(0, 5, '[2] Doe, J. and Johnson, R. (2022). Optimization in Quantum Systems. Physical Review A, 98(4), 042301.')
    pdf.multi_cell(0, 5, '[3] Brown, A. (2021). Mathematical Methods for Quantum Computing. Cambridge University Press.')
    
    # Save PDF
    pdf.output(str(pdf_path))
    
    return pdf_path


def create_synthetic_pdf_minimal() -> Path:
    """
    Create a minimal synthetic PDF using basic text content when no PDF libraries are available.
    
    Returns:
        Path to the created synthetic PDF file
    """
    pdf_path = PDFS_DIR / "test_paper.pdf"
    
    # Create a minimal PDF using basic PDF structure
    # This is a very basic PDF that should be parseable by most PDF libraries
    pdf_content = """%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 5 0 R
>>
>>
>>
endobj

4 0 obj
<<
/Length 800
>>
stream
BT
/F1 12 Tf
50 750 Td
(A Novel Approach to Quantum Computing Optimization) Tj
0 -30 Td
(John Smith, Jane Doe, Robert Johnson) Tj
0 -40 Td
(Abstract) Tj
0 -20 Td
(This paper presents a novel optimization algorithm for quantum computing systems.) Tj
0 -15 Td
(We demonstrate significant improvements in computational efficiency through the use) Tj
0 -15 Td
(of advanced mathematical techniques. Our approach shows a 40% reduction in) Tj
0 -15 Td
(processing time compared to existing methods.) Tj
0 -30 Td
(1. Introduction) Tj
0 -20 Td
(Quantum computing represents a paradigm shift in computational capabilities.) Tj
0 -15 Td
(Traditional algorithms face limitations when dealing with complex optimization) Tj
0 -15 Td
(problems. This research addresses these challenges through innovative mathematical) Tj
0 -15 Td
(modeling and algorithmic design.) Tj
0 -30 Td
(2. Methods) Tj
0 -20 Td
(Our optimization algorithm is based on the following mathematical framework.) Tj
0 -15 Td
(The core equation governing our approach is shown below:) Tj
0 -20 Td
([EQUATION] H = sum(alpha_i |psi_i><psi_i|) + beta * sum(J_ij * sigma_i^z * sigma_j^z)) Tj
0 -30 Td
(3. Results) Tj
0 -20 Td
(Our experimental results demonstrate the effectiveness of the proposed algorithm.) Tj
0 -15 Td
(Figure 1 shows the performance comparison between our method and existing approaches.) Tj
0 -15 Td
(The optimization converges significantly faster while maintaining solution quality.) Tj
0 -20 Td
(Figure 1: Performance comparison showing 40% improvement in convergence time.) Tj
ET
endstream
endobj

5 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000245 00000 n 
0000001097 00000 n 
trailer
<<
/Size 6
/Root 1 0 R
>>
startxref
1164
%%EOF"""
    
    with open(pdf_path, 'w', encoding='latin-1') as f:
        f.write(pdf_content)
    
    return pdf_path


def create_synthetic_pdf() -> Path:
    """
    Create a synthetic PDF with body text, equations, and figures for testing.
    
    Returns:
        Path to the created synthetic PDF file
    """
    logger.info("Creating synthetic PDF for testing")
    
    # Ensure PDFs directory exists
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        if REPORTLAB_AVAILABLE:
            logger.info("Using reportlab to create PDF")
            pdf_path = create_synthetic_pdf_reportlab()
        elif FPDF2_AVAILABLE:
            logger.info("Using fpdf2 to create PDF")
            pdf_path = create_synthetic_pdf_fpdf2()
        else:
            logger.info("Using minimal PDF creation (no PDF libraries available)")
            pdf_path = create_synthetic_pdf_minimal()
        
        logger.info(f"Successfully created synthetic PDF: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        logger.error(f"Failed to create synthetic PDF: {e}")
        logger.error("Expected: successful PDF creation")
        logger.error("Action: check PDF library installation and file permissions")
        raise


def run_pipeline_stage(script_name: str, timeout: int = 300) -> Tuple[int, str, str]:
    """
    Run a pipeline stage script as a subprocess.
    
    Args:
        script_name: Name of the Python script to run (e.g., "01_ingest.py")
        timeout: Timeout in seconds for the subprocess
        
    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    script_path = WORKSPACE_ROOT / script_name
    
    if not script_path.exists():
        raise FileNotFoundError(f"Pipeline script not found: {script_path}")
    
    logger.info(f"Running pipeline stage: {script_name}")
    
    try:
        # Run script as subprocess
        result = subprocess.run(
            ["python", str(script_path)],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return result.returncode, result.stdout, result.stderr
        
    except subprocess.TimeoutExpired:
        logger.error(f"Pipeline stage {script_name} timed out after {timeout} seconds")
        return -1, "", f"Timeout after {timeout} seconds"
    except Exception as e:
        logger.error(f"Failed to run pipeline stage {script_name}: {e}")
        return -1, "", str(e)


def validate_ingest_output() -> bool:
    """
    Validate that the ingest stage produced expected outputs.
    
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating ingest stage output")
    
    try:
        # Check manifest.json exists
        manifest_path = DATA_DIR / "manifest.json"
        if not manifest_path.exists():
            logger.error(f"Manifest file not found: {manifest_path}")
            return False
        
        # Check manifest contains at least one entry
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        
        if not manifest_data or len(manifest_data) == 0:
            logger.error("Manifest file is empty")
            return False
        
        # Check that the test paper is in the manifest
        test_paper_found = False
        for entry in manifest_data:
            if entry.get("filename") == "test_paper.pdf":
                test_paper_found = True
                break
        
        if not test_paper_found:
            logger.error("Test paper not found in manifest")
            return False
        
        logger.info("Ingest stage validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Ingest validation failed: {e}")
        return False


def validate_parse_output() -> bool:
    """
    Validate that the parse stage produced expected outputs.
    
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating parse stage output")
    
    try:
        # Check that at least one _merged.md file exists
        merged_files = list(PARSED_DIR.glob("*_merged.md"))
        
        if not merged_files:
            logger.error("No merged Markdown files found in parsed directory")
            return False
        
        # Check that test_paper_merged.md exists and is non-empty
        test_merged_path = PARSED_DIR / "test_paper_merged.md"
        if not test_merged_path.exists():
            logger.error(f"Test paper merged file not found: {test_merged_path}")
            return False
        
        # Check file is non-empty
        if test_merged_path.stat().st_size == 0:
            logger.error("Test paper merged file is empty")
            return False
        
        logger.info("Parse stage validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Parse validation failed: {e}")
        return False


def validate_chunk_output() -> bool:
    """
    Validate that the chunk stage produced expected outputs.
    
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating chunk stage output")
    
    try:
        # Check all_chunks.json exists
        chunks_path = PARSED_DIR / "all_chunks.json"
        if not chunks_path.exists():
            logger.error(f"All chunks file not found: {chunks_path}")
            return False
        
        # Check file is non-empty
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        if not chunks_data or len(chunks_data) == 0:
            logger.error("All chunks file is empty")
            return False
        
        # Check that chunks have expected structure
        first_chunk = chunks_data[0]
        required_keys = ["text", "metadata"]
        for key in required_keys:
            if key not in first_chunk:
                logger.error(f"Chunk missing required key: {key}")
                return False
        
        logger.info(f"Chunk stage validation passed ({len(chunks_data)} chunks)")
        return True
        
    except Exception as e:
        logger.error(f"Chunk validation failed: {e}")
        return False


def validate_index_output() -> bool:
    """
    Validate that the index stage produced expected outputs.
    
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating index stage output")
    
    try:
        # Check ChromaDB collection exists and has documents
        client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
        collection = client.get_collection("lit_review")
        
        doc_count = collection.count()
        if doc_count == 0:
            logger.error("ChromaDB collection is empty")
            return False
        
        # Check BM25 index exists
        bm25_path = VECTORSTORE_DIR / "bm25_index.pkl"
        if not bm25_path.exists():
            logger.error(f"BM25 index file not found: {bm25_path}")
            return False
        
        # Check BM25 index is valid
        with open(bm25_path, 'rb') as f:
            bm25_data = pickle.load(f)
        
        if "index" not in bm25_data or "chunk_ids" not in bm25_data:
            logger.error("BM25 index file has invalid structure")
            return False
        
        logger.info(f"Index stage validation passed ({doc_count} documents indexed)")
        return True
        
    except Exception as e:
        logger.error(f"Index validation failed: {e}")
        return False


def validate_query_output() -> bool:
    """
    Validate that the query stage works correctly.
    
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating query stage output")
    
    try:
        # Run a test query
        test_query = "quantum computing optimization algorithm"
        query_script = WORKSPACE_ROOT / "05_query.py"
        
        result = subprocess.run(
            ["python", str(query_script), test_query],
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            logger.error(f"Query script failed with exit code {result.returncode}")
            logger.error(f"Stderr: {result.stderr}")
            return False
        
        # Check that output is non-empty
        if not result.stdout.strip():
            logger.error("Query script returned empty output")
            return False
        
        # Check that output contains expected sections
        output = result.stdout
        if "QUERY RESULTS" not in output or "Answer:" not in output:
            logger.error("Query output missing expected sections")
            return False
        
        logger.info("Query stage validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Query validation failed: {e}")
        return False


def validate_review_output() -> bool:
    """
    Validate that the review stage produced expected outputs.
    
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating review stage output")
    
    try:
        # Check literature review file exists
        review_path = SUMMARIES_DIR / "literature_review.md"
        if not review_path.exists():
            logger.error(f"Literature review file not found: {review_path}")
            return False
        
        # Check file is non-empty
        if review_path.stat().st_size == 0:
            logger.error("Literature review file is empty")
            return False
        
        # Check that summary files exist
        summary_files = list(SUMMARIES_DIR.glob("*_summary.json"))
        if not summary_files:
            logger.error("No summary files found")
            return False
        
        # Check that test paper summary exists
        test_summary_path = SUMMARIES_DIR / "test_paper_summary.json"
        if not test_summary_path.exists():
            logger.error(f"Test paper summary not found: {test_summary_path}")
            return False
        
        logger.info("Review stage validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Review validation failed: {e}")
        return False


def cleanup_test_data() -> None:
    """Clean up test data and directories."""
    logger.info("Cleaning up test data")
    
    try:
        # Remove test PDF
        test_pdf = PDFS_DIR / "test_paper.pdf"
        if test_pdf.exists():
            test_pdf.unlink()
        
        # Remove generated files (but keep directories for next run)
        files_to_remove = [
            DATA_DIR / "manifest.json",
            PARSED_DIR / "test_paper_merged.md",
            PARSED_DIR / "test_paper_chunks.json",
            PARSED_DIR / "all_chunks.json",
            SUMMARIES_DIR / "test_paper_summary.json",
            SUMMARIES_DIR / "literature_review.md",
            VECTORSTORE_DIR / "bm25_index.pkl"
        ]
        
        for file_path in files_to_remove:
            if file_path.exists():
                file_path.unlink()
        
        # Remove ChromaDB data
        if VECTORSTORE_DIR.exists():
            import shutil
            chroma_dirs = [d for d in VECTORSTORE_DIR.iterdir() if d.is_dir()]
            for chroma_dir in chroma_dirs:
                shutil.rmtree(chroma_dir, ignore_errors=True)
        
        logger.info("Test data cleanup completed")
        
    except Exception as e:
        logger.warning(f"Cleanup failed (non-critical): {e}")


def run_integration_test() -> List[PipelineTestResult]:
    """
    Run the complete integration test pipeline.
    
    Returns:
        List of PipelineTestResult objects for each stage
    """
    logger.info("Starting end-to-end integration test")
    
    # Pipeline stages configuration
    stages = [
        ("01_ingest.py", "Ingest", validate_ingest_output),
        ("02_parse.py", "Parse", validate_parse_output),
        ("03_chunk.py", "Chunk", validate_chunk_output),
        ("04_index.py", "Index", validate_index_output),
        ("05_query.py", "Query", validate_query_output),
        ("06_review.py", "Review", validate_review_output)
    ]
    
    results = []
    
    try:
        # Clean up any existing test data
        cleanup_test_data()
        
        # Create synthetic PDF
        create_synthetic_pdf()
        
        # Run each pipeline stage
        for script_name, phase_name, validator in stages:
            result = PipelineTestResult(phase_name)
            
            logger.info(f"Testing {phase_name} stage ({script_name})")
            start_time = time.time()
            
            try:
                # Skip query stage subprocess run (use validator directly)
                if script_name == "05_query.py":
                    result.exit_code = 0
                    result.passed = validator()
                else:
                    # Run pipeline stage
                    exit_code, stdout, stderr = run_pipeline_stage(script_name)
                    result.exit_code = exit_code
                    
                    if exit_code == 0:
                        # Validate output
                        result.passed = validator()
                        if not result.passed:
                            result.error_message = f"Output validation failed for {phase_name}"
                    else:
                        result.passed = False
                        result.error_message = f"Script failed with exit code {exit_code}: {stderr}"
                
            except Exception as e:
                result.passed = False
                result.error_message = f"Exception during {phase_name}: {str(e)}"
            
            result.elapsed_time = time.time() - start_time
            results.append(result)
            
            # Log result
            status = "PASS" if result.passed else "FAIL"
            logger.info(f"{phase_name} stage: {status} ({result.elapsed_time:.2f}s)")
            
            if not result.passed:
                logger.error(f"{phase_name} stage failed: {result.error_message}")
                # Continue with remaining stages to get full picture
        
        return results
        
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        # Create a failure result for the current stage
        failure_result = PipelineTestResult("Setup")
        failure_result.passed = False
        failure_result.error_message = str(e)
        results.append(failure_result)
        return results
    
    finally:
        # Clean up test data
        cleanup_test_data()


def print_test_report(results: List[PipelineTestResult]) -> None:
    """
    Print a formatted test report.
    
    Args:
        results: List of PipelineTestResult objects
    """
    print("\n" + "="*80)
    print("PIPELINE INTEGRATION TEST REPORT")
    print("="*80)
    
    total_time = sum(r.elapsed_time for r in results)
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    
    print(f"\nOverall Result: {passed_count}/{total_count} stages passed")
    print(f"Total Execution Time: {total_time:.2f} seconds")
    print("\nStage Results:")
    print("-" * 60)
    
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{result.phase_name:<15} {status:<6} {result.elapsed_time:>8.2f}s")
        
        if not result.passed:
            print(f"                Error: {result.error_message}")
            if result.exit_code is not None:
                print(f"                Exit Code: {result.exit_code}")
    
    print("-" * 60)
    
    if passed_count == total_count:
        print("\n✅ All pipeline stages passed successfully!")
        print("The literature review pipeline is working correctly.")
    else:
        print(f"\n❌ {total_count - passed_count} pipeline stage(s) failed.")
        print("Please check the logs and fix the issues before proceeding.")
    
    print("\nTest completed.")


def main() -> None:
    """Main test execution function."""
    logger.info("Starting pipeline integration test")
    
    try:
        # Run integration test
        results = run_integration_test()
        
        # Print report
        print_test_report(results)
        
        # Exit with appropriate code
        all_passed = all(r.passed for r in results)
        exit_code = 0 if all_passed else 1
        
        logger.info(f"Integration test completed with exit code {exit_code}")
        exit(exit_code)
        
    except Exception as e:
        logger.error(f"Integration test failed with exception: {e}")
        print(f"\nFatal Error: {e}")
        print("Integration test could not complete.")
        exit(1)


if __name__ == "__main__":
    main()