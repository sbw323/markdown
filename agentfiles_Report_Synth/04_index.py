"""
Embedding and vector store indexing pipeline stage.

Loads all_chunks.json and creates dual indexing with ChromaDB for semantic search
and BM25 for keyword search. Handles equation content preprocessing for embeddings.
"""

import json
import logging
import pickle
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from config import PARSED_DIR, VECTORSTORE_DIR, EMBEDDING_MODEL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_chunks() -> List[Dict[str, Any]]:
    """
    Load all chunks from the aggregated chunks file.
    
    Returns:
        List of chunk dictionaries with text and metadata
        
    Raises:
        FileNotFoundError: If all_chunks.json does not exist
        json.JSONDecodeError: If all_chunks.json is not valid JSON
        ValueError: If chunks file is empty
    """
    chunks_path = PARSED_DIR / "all_chunks.json"
    
    if not chunks_path.exists():
        logger.error(f"Chunks file not found: {chunks_path}")
        logger.error("Expected: all_chunks.json created by 03_chunk.py")
        logger.error("Action: run 03_chunk.py first to generate chunks")
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")
    
    try:
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        if not chunks:
            logger.error("Chunks file is empty")
            logger.error("Expected: non-empty list of chunks")
            logger.error("Action: check 03_chunk.py output or regenerate chunks")
            raise ValueError("Chunks file is empty")
        
        logger.info(f"Loaded {len(chunks)} chunks from {chunks_path}")
        return chunks
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in chunks file: {e}")
        logger.error("Expected: valid JSON format")
        logger.error("Action: check all_chunks.json file integrity or regenerate with 03_chunk.py")
        raise


def strip_equation_content(text: str) -> str:
    """
    Strip LaTeX equation content from text for embedding purposes.
    
    Args:
        text: Original text with LaTeX equations
        
    Returns:
        Text with equation content removed but structure preserved
    """
    # Remove display equations ($$...$$) but keep [EQUATION] markers
    text = re.sub(r'\[EQUATION\]\s*\$\$[^$]*\$\$', '[EQUATION]', text, flags=re.DOTALL)
    
    # Remove inline equations ($...$) but keep [EQUATION] markers
    text = re.sub(r'\[EQUATION\]\s*\$[^$\n]+\$', '[EQUATION]', text)
    
    # Remove any remaining LaTeX equations without [EQUATION] markers
    text = re.sub(r'\$\$[^$]*\$\$', '', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\$)\$[^$\n]+\$(?!\$)', '', text)
    
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def preprocess_chunk_for_embedding(chunk: Dict[str, Any]) -> str:
    """
    Preprocess a chunk for embedding based on equation content.
    
    Args:
        chunk: Chunk dictionary with text and metadata
        
    Returns:
        Preprocessed text suitable for embedding
    """
    text = chunk["text"]
    has_equations = chunk["metadata"].get("has_equations", False)
    
    if has_equations:
        # Strip equation content but preserve structure
        processed_text = strip_equation_content(text)
        logger.debug(f"Stripped equations from chunk {chunk['metadata'].get('paper_id', 'unknown')}")
    else:
        processed_text = text
    
    return processed_text


def create_chromadb_collection() -> chromadb.Collection:
    """
    Create or recreate ChromaDB collection for vector storage.
    
    Returns:
        ChromaDB collection object
        
    Raises:
        Exception: If ChromaDB initialization fails
    """
    logger.info("Initializing ChromaDB collection")
    
    # Ensure vectorstore directory exists
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        # Initialize ChromaDB client with persistent storage
        client = chromadb.PersistentClient(
            path=str(VECTORSTORE_DIR),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Delete existing collection if it exists (idempotent behavior)
        try:
            client.delete_collection(name="lit_review")
            logger.info("Deleted existing ChromaDB collection")
        except Exception:
            # Collection doesn't exist, which is fine
            pass
        
        # Create new collection
        collection = client.create_collection(
            name="lit_review",
            metadata={"description": "Scientific literature review chunks"}
        )
        
        logger.info("Created new ChromaDB collection 'lit_review'")
        return collection
        
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB collection: {e}")
        logger.error("Expected: successful ChromaDB initialization")
        logger.error("Action: check vectorstore directory permissions and ChromaDB installation")
        raise


def embed_chunks(chunks: List[Dict[str, Any]], collection: chromadb.Collection) -> None:
    """
    Embed all chunks and store in ChromaDB collection.
    
    Args:
        chunks: List of chunk dictionaries
        collection: ChromaDB collection to store embeddings
        
    Raises:
        Exception: If embedding or storage fails
    """
    logger.info(f"Embedding {len(chunks)} chunks using model: {EMBEDDING_MODEL}")
    
    try:
        # Initialize sentence transformer model
        model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info(f"Loaded embedding model: {EMBEDDING_MODEL}")
        
        # Prepare data for batch processing
        chunk_ids = []
        chunk_texts = []
        embedding_texts = []
        chunk_metadatas = []
        
        for i, chunk in enumerate(chunks):
            # Generate unique ID for chunk
            paper_id = chunk["metadata"].get("paper_id", "unknown")
            section = chunk["metadata"].get("section", "unknown")
            chunk_index = chunk["metadata"].get("chunk_index", 0)
            chunk_id = f"{paper_id}_{section}_{chunk_index}_{i}"
            
            # Prepare texts
            original_text = chunk["text"]
            embedding_text = preprocess_chunk_for_embedding(chunk)
            
            # Prepare metadata (ChromaDB requires string values)
            metadata = {
                "paper_id": str(chunk["metadata"].get("paper_id", "")),
                "title": str(chunk["metadata"].get("title", "")),
                "authors": str(chunk["metadata"].get("authors", [])),
                "year": str(chunk["metadata"].get("year", "")),
                "journal": str(chunk["metadata"].get("journal", "")),
                "doi": str(chunk["metadata"].get("doi", "")),
                "section": str(chunk["metadata"].get("section", "")),
                "chunk_index": str(chunk["metadata"].get("chunk_index", 0)),
                "has_equations": str(chunk["metadata"].get("has_equations", False)),
                "has_figures": str(chunk["metadata"].get("has_figures", False)),
                "page_numbers": str(chunk["metadata"].get("page_numbers", []))
            }
            
            chunk_ids.append(chunk_id)
            chunk_texts.append(original_text)  # Store original text with equations
            embedding_texts.append(embedding_text)  # Use processed text for embedding
            chunk_metadatas.append(metadata)
        
        # Generate embeddings in batches
        batch_size = 32
        logger.info(f"Generating embeddings in batches of {batch_size}")
        
        for i in range(0, len(embedding_texts), batch_size):
            batch_end = min(i + batch_size, len(embedding_texts))
            batch_texts = embedding_texts[i:batch_end]
            batch_ids = chunk_ids[i:batch_end]
            batch_documents = chunk_texts[i:batch_end]
            batch_metadatas = chunk_metadatas[i:batch_end]
            
            # Generate embeddings for this batch
            embeddings = model.encode(batch_texts, convert_to_tensor=False)
            embeddings_list = embeddings.tolist()
            
            # Add to ChromaDB collection
            collection.add(
                ids=batch_ids,
                embeddings=embeddings_list,
                documents=batch_documents,  # Store original text
                metadatas=batch_metadatas
            )
            
            logger.debug(f"Processed batch {i//batch_size + 1}/{(len(embedding_texts) + batch_size - 1)//batch_size}")
        
        logger.info(f"Successfully embedded and stored {len(chunks)} chunks in ChromaDB")
        
    except Exception as e:
        logger.error(f"Failed to embed chunks: {e}")
        logger.error("Expected: successful embedding generation and ChromaDB storage")
        logger.error("Action: check sentence-transformers installation and model availability")
        raise


def build_bm25_index(chunks: List[Dict[str, Any]]) -> None:
    """
    Build BM25 index over all chunk texts and save to pickle file.
    
    Args:
        chunks: List of chunk dictionaries
        
    Raises:
        Exception: If BM25 index creation or saving fails
    """
    logger.info(f"Building BM25 index over {len(chunks)} chunks")
    
    try:
        # Prepare texts and chunk IDs
        chunk_texts = []
        chunk_ids = []
        
        for i, chunk in enumerate(chunks):
            # Use original text for BM25 (including equations)
            text = chunk["text"]
            chunk_texts.append(text)
            
            # Generate same ID as used in ChromaDB
            paper_id = chunk["metadata"].get("paper_id", "unknown")
            section = chunk["metadata"].get("section", "unknown")
            chunk_index = chunk["metadata"].get("chunk_index", 0)
            chunk_id = f"{paper_id}_{section}_{chunk_index}_{i}"
            chunk_ids.append(chunk_id)
        
        # Tokenize texts for BM25
        logger.info("Tokenizing texts for BM25 index")
        tokenized_texts = [text.split() for text in chunk_texts]
        
        # Build BM25 index
        logger.info("Building BM25Okapi index")
        bm25_index = BM25Okapi(tokenized_texts)
        
        # Prepare data to pickle
        bm25_data = {
            "index": bm25_index,
            "chunk_ids": chunk_ids,
            "chunk_texts": chunk_texts
        }
        
        # Save to pickle file (idempotent - overwrites existing)
        bm25_path = VECTORSTORE_DIR / "bm25_index.pkl"
        with open(bm25_path, 'wb') as f:
            pickle.dump(bm25_data, f)
        
        logger.info(f"Successfully built and saved BM25 index to {bm25_path}")
        
    except Exception as e:
        logger.error(f"Failed to build BM25 index: {e}")
        logger.error("Expected: successful BM25 index creation and pickle saving")
        logger.error("Action: check rank-bm25 installation and vectorstore directory permissions")
        raise


def validate_indexes(chunks: List[Dict[str, Any]]) -> None:
    """
    Validate that both indexes were created successfully.
    
    Args:
        chunks: Original chunks list for validation
        
    Raises:
        Exception: If validation fails
    """
    logger.info("Validating created indexes")
    
    try:
        # Validate ChromaDB collection
        client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
        collection = client.get_collection("lit_review")
        
        chroma_count = collection.count()
        if chroma_count != len(chunks):
            raise ValueError(f"ChromaDB count mismatch: expected {len(chunks)}, got {chroma_count}")
        
        logger.info(f"ChromaDB validation passed: {chroma_count} documents")
        
        # Validate BM25 pickle
        bm25_path = VECTORSTORE_DIR / "bm25_index.pkl"
        if not bm25_path.exists():
            raise FileNotFoundError(f"BM25 pickle file not found: {bm25_path}")
        
        with open(bm25_path, 'rb') as f:
            bm25_data = pickle.load(f)
        
        if len(bm25_data["chunk_ids"]) != len(chunks):
            raise ValueError(f"BM25 count mismatch: expected {len(chunks)}, got {len(bm25_data['chunk_ids'])}")
        
        logger.info(f"BM25 validation passed: {len(bm25_data['chunk_ids'])} documents")
        
        logger.info("Index validation completed successfully")
        
    except Exception as e:
        logger.error(f"Index validation failed: {e}")
        logger.error("Expected: both indexes to contain correct number of documents")
        logger.error("Action: check index creation process and file integrity")
        raise


def main() -> None:
    """Main pipeline execution function."""
    logger.info("Starting embedding and vector store indexing pipeline")

    try:
        chunks = load_chunks()
        collection = create_chromadb_collection()
        embed_chunks(chunks, collection)
        build_bm25_index(chunks)

        # Validate using the SAME collection object — no second client
        chroma_count = collection.count()
        if chroma_count != len(chunks):
            raise ValueError(f"ChromaDB count mismatch: expected {len(chunks)}, got {chroma_count}")
        logger.info(f"ChromaDB validation passed: {chroma_count} documents")

        bm25_path = VECTORSTORE_DIR / "bm25_index.pkl"
        if not bm25_path.exists():
            raise FileNotFoundError(f"BM25 pickle file not found: {bm25_path}")
        with open(bm25_path, 'rb') as f:
            bm25_data = pickle.load(f)
        if len(bm25_data["chunk_ids"]) != len(chunks):
            raise ValueError(f"BM25 count mismatch: expected {len(chunks)}, got {len(bm25_data['chunk_ids'])}")
        logger.info(f"BM25 validation passed: {len(bm25_data['chunk_ids'])} documents")

        equation_chunks = sum(1 for c in chunks if c["metadata"].get("has_equations", False))
        figure_chunks = sum(1 for c in chunks if c["metadata"].get("has_figures", False))
        logger.info(f"Total chunks indexed: {len(chunks)}")
        logger.info(f"Chunks with equations: {equation_chunks}")
        logger.info(f"Chunks with figures: {figure_chunks}")
        logger.info("Pipeline completed successfully")

    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}")
        logger.error("Expected: successful dual indexing with ChromaDB and BM25")
        logger.error("Action: check chunk availability, embedding model, and vectorstore configuration")
        raise


if __name__ == "__main__":
    main()