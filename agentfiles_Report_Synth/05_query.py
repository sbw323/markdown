"""
Hybrid retrieval and query pipeline stage.

Performs dense and sparse retrieval, fuses results using RRF, optionally reranks,
and generates answers using Claude LLM with source citations.
"""

import argparse
import json
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

import chromadb
from sentence_transformers import SentenceTransformer

# Optional dependencies for reranking
try:
    from sentence_transformers import CrossEncoder
    RERANKING_AVAILABLE = True
except ImportError:
    RERANKING_AVAILABLE = False

# Optional dependency for Anthropic API
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from config import (
    VECTORSTORE_DIR, EMBEDDING_MODEL, ANTHROPIC_API_KEY, PIPELINE_MODEL
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Retrieval configuration
DENSE_TOP_K = 15
SPARSE_TOP_K = 15
RRF_K = 60
FINAL_TOP_K = 8
ENABLE_RERANKING = False  # Set to True to enable cross-encoder reranking
RERANKING_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class HybridRetriever:
    """Handles hybrid retrieval using dense and sparse methods with RRF fusion."""
    
    def __init__(self) -> None:
        """Initialize the hybrid retriever."""
        self.embedding_model = None
        self.chroma_collection = None
        self.bm25_data = None
        self.reranker = None
        self.anthropic_client = None
        
        # Initialize components
        self._load_embedding_model()
        self._load_chroma_collection()
        self._load_bm25_index()
        self._load_reranker()
        self._load_anthropic_client()
    
    def _load_embedding_model(self) -> None:
        """Load the sentence transformer model for dense retrieval."""
        try:
            logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
            self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Successfully loaded embedding model")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            logger.error("Expected: successful model loading")
            logger.error("Action: check sentence-transformers installation and model availability")
            raise
    
    def _load_chroma_collection(self) -> None:
        """Load the ChromaDB collection for dense retrieval."""
        try:
            logger.info("Loading ChromaDB collection")
            client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
            self.chroma_collection = client.get_collection("lit_review")
            
            doc_count = self.chroma_collection.count()
            logger.info(f"Successfully loaded ChromaDB collection with {doc_count} documents")
            
        except Exception as e:
            logger.error(f"Failed to load ChromaDB collection: {e}")
            logger.error("Expected: existing ChromaDB collection from 04_index.py")
            logger.error("Action: run 04_index.py first to create the vector index")
            raise
    
    def _load_bm25_index(self) -> None:
        """Load the BM25 index for sparse retrieval."""
        bm25_path = VECTORSTORE_DIR / "bm25_index.pkl"
        
        if not bm25_path.exists():
            logger.error(f"BM25 index not found: {bm25_path}")
            logger.error("Expected: BM25 index file from 04_index.py")
            logger.error("Action: run 04_index.py first to create the BM25 index")
            raise FileNotFoundError(f"BM25 index not found: {bm25_path}")
        
        try:
            logger.info("Loading BM25 index")
            with open(bm25_path, 'rb') as f:
                self.bm25_data = pickle.load(f)
            
            doc_count = len(self.bm25_data["chunk_ids"])
            logger.info(f"Successfully loaded BM25 index with {doc_count} documents")
            
        except Exception as e:
            logger.error(f"Failed to load BM25 index: {e}")
            logger.error("Expected: valid BM25 pickle file")
            logger.error("Action: check file integrity or regenerate with 04_index.py")
            raise
    
    def _load_reranker(self) -> None:
        """Load the cross-encoder model for reranking if enabled."""
        if not ENABLE_RERANKING:
            logger.info("Reranking disabled")
            return
        
        if not RERANKING_AVAILABLE:
            logger.warning("Reranking enabled but cross-encoder not available")
            logger.warning("Install sentence-transformers with cross-encoder support")
            return
        
        try:
            logger.info(f"Loading reranking model: {RERANKING_MODEL}")
            self.reranker = CrossEncoder(RERANKING_MODEL)
            logger.info("Successfully loaded reranking model")
        except Exception as e:
            logger.warning(f"Failed to load reranking model: {e}")
            logger.warning("Continuing without reranking")
    
    def _load_anthropic_client(self) -> None:
        """Load the Anthropic client for LLM calls."""
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
            self.anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
            logger.info("Successfully initialized Anthropic client")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            logger.error("Expected: valid API key and client initialization")
            logger.error("Action: check API key validity and network connection")
            raise
    
    def dense_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform dense retrieval using ChromaDB.
        
        Args:
            query: Search query string
            
        Returns:
            List of retrieved chunks with metadata and scores
        """
        logger.info(f"Performing dense retrieval for query: {query[:100]}...")
        
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])[0].tolist()
            
            # Search ChromaDB
            results = self.chroma_collection.query(
                query_embeddings=[query_embedding],
                n_results=DENSE_TOP_K,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            retrieved_chunks = []
            for i in range(len(results["ids"][0])):
                chunk = {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": 1.0 / (1.0 + results["distances"][0][i]),  # Convert distance to similarity
                    "method": "dense"
                }
                retrieved_chunks.append(chunk)
            
            logger.info(f"Dense retrieval returned {len(retrieved_chunks)} chunks")
            return retrieved_chunks
            
        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}")
            logger.error("Expected: successful ChromaDB query")
            logger.error("Action: check ChromaDB collection and embedding model")
            raise
    
    def sparse_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform sparse retrieval using BM25.
        
        Args:
            query: Search query string
            
        Returns:
            List of retrieved chunks with metadata and scores
        """
        logger.info(f"Performing sparse retrieval for query: {query[:100]}...")
        
        try:
            # Tokenize query
            query_tokens = query.split()
            
            # Get BM25 scores
            bm25_scores = self.bm25_data["index"].get_scores(query_tokens)
            
            # Get top-k results
            top_indices = sorted(
                range(len(bm25_scores)), 
                key=lambda i: bm25_scores[i], 
                reverse=True
            )[:SPARSE_TOP_K]
            
            # Format results
            retrieved_chunks = []
            for idx in top_indices:
                # Get chunk metadata from ChromaDB using chunk ID
                chunk_id = self.bm25_data["chunk_ids"][idx]
                
                try:
                    chroma_result = self.chroma_collection.get(
                        ids=[chunk_id],
                        include=["documents", "metadatas"]
                    )
                    
                    if chroma_result["ids"]:
                        chunk = {
                            "id": chunk_id,
                            "text": chroma_result["documents"][0],
                            "metadata": chroma_result["metadatas"][0],
                            "score": float(bm25_scores[idx]),
                            "method": "sparse"
                        }
                        retrieved_chunks.append(chunk)
                    
                except Exception as e:
                    logger.warning(f"Failed to get metadata for chunk {chunk_id}: {e}")
                    # Fallback to BM25 data only
                    chunk = {
                        "id": chunk_id,
                        "text": self.bm25_data["chunk_texts"][idx],
                        "metadata": {},
                        "score": float(bm25_scores[idx]),
                        "method": "sparse"
                    }
                    retrieved_chunks.append(chunk)
            
            logger.info(f"Sparse retrieval returned {len(retrieved_chunks)} chunks")
            return retrieved_chunks
            
        except Exception as e:
            logger.error(f"Sparse retrieval failed: {e}")
            logger.error("Expected: successful BM25 scoring and retrieval")
            logger.error("Action: check BM25 index and query processing")
            raise
    
    def reciprocal_rank_fusion(self, dense_results: List[Dict[str, Any]], 
                              sparse_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fuse dense and sparse results using Reciprocal Rank Fusion.
        
        Args:
            dense_results: Results from dense retrieval
            sparse_results: Results from sparse retrieval
            
        Returns:
            List of fused results sorted by RRF score
        """
        logger.info("Performing Reciprocal Rank Fusion")
        
        # Collect all unique chunks
        chunk_scores = {}
        
        # Process dense results
        for rank, chunk in enumerate(dense_results):
            chunk_id = chunk["id"]
            rrf_score = 1.0 / (RRF_K + rank + 1)
            
            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": 0.0,
                    "dense_rank": None,
                    "sparse_rank": None
                }
            
            chunk_scores[chunk_id]["rrf_score"] += rrf_score
            chunk_scores[chunk_id]["dense_rank"] = rank + 1
        
        # Process sparse results
        for rank, chunk in enumerate(sparse_results):
            chunk_id = chunk["id"]
            rrf_score = 1.0 / (RRF_K + rank + 1)
            
            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": 0.0,
                    "dense_rank": None,
                    "sparse_rank": None
                }
            
            chunk_scores[chunk_id]["rrf_score"] += rrf_score
            chunk_scores[chunk_id]["sparse_rank"] = rank + 1
        
        # Sort by RRF score and take top-k
        sorted_chunks = sorted(
            chunk_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )[:FINAL_TOP_K]
        
        # Format results
        fused_results = []
        for item in sorted_chunks:
            chunk = item["chunk"].copy()
            chunk["rrf_score"] = item["rrf_score"]
            chunk["dense_rank"] = item["dense_rank"]
            chunk["sparse_rank"] = item["sparse_rank"]
            fused_results.append(chunk)
        
        logger.info(f"RRF fusion returned {len(fused_results)} chunks")
        return fused_results
    
    def rerank_results(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rerank candidates using cross-encoder model.
        
        Args:
            query: Original search query
            candidates: List of candidate chunks to rerank
            
        Returns:
            List of reranked chunks
        """
        if not self.reranker or not ENABLE_RERANKING:
            logger.info("Reranking disabled or unavailable, returning original order")
            return candidates
        
        logger.info(f"Reranking {len(candidates)} candidates")
        
        try:
            # Prepare query-document pairs
            query_doc_pairs = []
            for candidate in candidates:
                query_doc_pairs.append([query, candidate["text"]])
            
            # Get reranking scores
            rerank_scores = self.reranker.predict(query_doc_pairs)
            
            # Add rerank scores and sort
            for i, candidate in enumerate(candidates):
                candidate["rerank_score"] = float(rerank_scores[i])
            
            reranked_results = sorted(
                candidates,
                key=lambda x: x["rerank_score"],
                reverse=True
            )
            
            logger.info("Successfully reranked candidates")
            return reranked_results
            
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            logger.warning("Returning original RRF order")
            return candidates
    
    def generate_answer(self, query: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """
        Generate answer using Claude LLM with retrieved chunks.
        
        Args:
            query: Original search query
            retrieved_chunks: List of retrieved and ranked chunks
            
        Returns:
            Generated answer text
        """
        logger.info("Generating answer using Claude LLM")
        
        try:
            # Construct prompt with retrieved chunks
            prompt = self._construct_prompt(query, retrieved_chunks)
            
            # Call Claude API
            response = self.anthropic_client.messages.create(
                model=PIPELINE_MODEL,
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            answer = response.content[0].text.strip()
            logger.info("Successfully generated answer")
            return answer
            
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            logger.error("Expected: successful Claude API call")
            logger.error("Action: check API key, model availability, and network connection")
            raise
    
    def _construct_prompt(self, query: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """
        Construct LLM prompt with query and retrieved chunks.
        
        Args:
            query: Original search query
            retrieved_chunks: List of retrieved chunks with metadata
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "You are a scientific literature review assistant. Answer the following question based on the provided research paper excerpts.",
            "",
            f"Question: {query}",
            "",
            "Research Paper Excerpts:",
            ""
        ]
        
        for i, chunk in enumerate(retrieved_chunks, 1):
            metadata = chunk["metadata"]
            
            # Extract metadata fields
            title = metadata.get("title", "Unknown Title")
            authors = metadata.get("authors", "Unknown Authors")
            year = metadata.get("year", "Unknown Year")
            section = metadata.get("section", "Unknown Section")
            
            # Format chunk with metadata header
            chunk_header = f"[{i}] {title} ({authors}, {year}) - {section}"
            chunk_text = chunk["text"]
            
            prompt_parts.extend([
                chunk_header,
                chunk_text,
                ""
            ])
        
        prompt_parts.extend([
            "Instructions:",
            "- Provide a comprehensive answer based on the research excerpts above",
            "- Cite specific papers using the format [1], [2], etc. corresponding to the numbered excerpts",
            "- Preserve any mathematical equations exactly as they appear in the source material",
            "- If the excerpts don't contain sufficient information to answer the question, state this clearly",
            "- Focus on scientific accuracy and cite your sources appropriately",
            "",
            "Answer:"
        ])
        
        return "\n".join(prompt_parts)
    
    def query(self, query_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Perform complete hybrid retrieval and answer generation.
        
        Args:
            query_text: Search query string
            
        Returns:
            Tuple of (answer_text, retrieved_chunks)
        """
        logger.info(f"Processing query: {query_text}")
        
        try:
            # Step 1: Dense retrieval
            dense_results = self.dense_retrieval(query_text)
            
            # Step 2: Sparse retrieval
            sparse_results = self.sparse_retrieval(query_text)
            
            # Step 3: Reciprocal Rank Fusion
            fused_results = self.reciprocal_rank_fusion(dense_results, sparse_results)
            
            # Step 4: Optional reranking
            final_results = self.rerank_results(query_text, fused_results)
            
            # Step 5: Generate answer
            answer = self.generate_answer(query_text, final_results)
            
            logger.info("Query processing completed successfully")
            return answer, final_results
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            logger.error("Expected: successful end-to-end query processing")
            logger.error("Action: check all pipeline components and dependencies")
            raise


def main() -> None:
    """Main function for command-line query processing."""
    parser = argparse.ArgumentParser(
        description="Query the scientific literature review system"
    )
    parser.add_argument(
        "query",
        type=str,
        help="Search query string"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize retriever
        logger.info("Initializing hybrid retriever")
        retriever = HybridRetriever()
        
        # Process query
        answer, retrieved_chunks = retriever.query(args.query)
        
        # Display results
        print("\n" + "="*80)
        print("QUERY RESULTS")
        print("="*80)
        print(f"\nQuery: {args.query}")
        print(f"\nAnswer:\n{answer}")
        
        print(f"\n\nSource Papers ({len(retrieved_chunks)} chunks retrieved):")
        print("-" * 60)
        
        seen_papers = set()
        for i, chunk in enumerate(retrieved_chunks, 1):
            metadata = chunk["metadata"]
            paper_key = (metadata.get("title", ""), metadata.get("year", ""))
            
            if paper_key not in seen_papers:
                seen_papers.add(paper_key)
                title = metadata.get("title", "Unknown Title")
                authors = metadata.get("authors", "Unknown Authors")
                year = metadata.get("year", "Unknown Year")
                journal = metadata.get("journal", "")
                
                print(f"[{len(seen_papers)}] {title}")
                print(f"    Authors: {authors}")
                print(f"    Year: {year}")
                if journal:
                    print(f"    Journal: {journal}")
                print()
        
        if args.verbose:
            print("\nDetailed Chunk Information:")
            print("-" * 60)
            for i, chunk in enumerate(retrieved_chunks, 1):
                metadata = chunk["metadata"]
                print(f"Chunk {i}:")
                print(f"  Paper: {metadata.get('title', 'Unknown')}")
                print(f"  Section: {metadata.get('section', 'Unknown')}")
                print(f"  Method: {chunk.get('method', 'Unknown')}")
                if 'rrf_score' in chunk:
                    print(f"  RRF Score: {chunk['rrf_score']:.4f}")
                if 'rerank_score' in chunk:
                    print(f"  Rerank Score: {chunk['rerank_score']:.4f}")
                print(f"  Text: {chunk['text'][:200]}...")
                print()
        
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        print(f"\nError: {e}")
        print("Please check the logs for more details.")
        exit(1)


if __name__ == "__main__":
    main()