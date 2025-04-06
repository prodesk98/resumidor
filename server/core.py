import asyncio
from typing import Optional

import torch
from transformers import AutoModel, AutoModelForSequenceClassification, pipeline

from .env import RERANKER_MODEL, EMBEDDING_MODEL, SUMMARIZATION_MODEL
from loggings import logger


class Embedding:
    def __init__(self, model: Optional[str] = None) -> None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger(f"Loading embedding model on {device}...", "info")

        self.device = device
        self._model = AutoModel.from_pretrained(
            model or EMBEDDING_MODEL,
            trust_remote_code=True,
        ).to(device)
        self._model.eval()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or not all(isinstance(t, str) and t.strip() for t in texts):
            raise ValueError("Input texts must be a non-empty list of non-empty strings.")

        logger(f"Generating embeddings for {len(texts)} texts.", "info")
        return [
            self._model.encode(text, task="text-matching", max_length=2048)
            for text in texts
        ]


class Reranker:
    def __init__(self, model: Optional[str] = None) -> None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger(f"Loading reranker model on {device}...", "info")

        self.device = device
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model or RERANKER_MODEL,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            trust_remote_code=True,
        ).to(device)
        self._model.eval()

    def rerank(self, query: str, documents: list[str]) -> tuple[list[str], list[float]]:
        if not query or not isinstance(query, str) or not query.strip():
            raise ValueError("Query must be a non-empty string.")
        if not documents:
            logger("Received empty documents list for reranking.", "warning")
            return [], []

        if len(documents) < 2:
            logger("No documents provided for reranking.", "warning")
            return [], []

        logger(f"Reranking {len(documents)} documents for query: {query}", "info")

        sentence_pairs = [[query, doc] for doc in documents]
        scores: list[float] = self._model.compute_score(sentence_pairs, max_length=1024)

        if len(documents) == 1:
            return [documents[0]], [scores[0]]

        reranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        reranked_documents, rerank_scores = zip(*reranked)

        return list(reranked_documents), list(rerank_scores)


class Summarization:
    def __init__(self, model: Optional[str] = None) -> None:
        self._summarizer = pipeline("summarization", model=model or SUMMARIZATION_MODEL)

    def summarize(self, query: str, text: str) -> str:
        if not text or not isinstance(text, str) or not text.strip():
            raise ValueError("Input text must be a non-empty string.")
        if not query or not isinstance(query, str) or not query.strip():
            raise ValueError("Query must be a non-empty string.")
        if len(text) > 4096:
            raise ValueError("Input text exceeds the maximum length of 4096 characters.")

        logger(f"Summarizing text of length {len(text)}.", "info")
        summaries: list[dict] = self._summarizer(
            f"**Query: {query}\n\n**{text}", max_length=150, min_length=30, do_sample=False)
        return summaries[0]['summary_text']


_embedding = Embedding()
_reranker = Reranker()
_summarization = Summarization()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(_embedding.embed, texts)


async def rerank_documents(query: str, documents: list[str]) -> tuple[list[str], list[float]]:
    return await asyncio.to_thread(_reranker.rerank, query, documents)


async def summarize_text(query: str, text: str) -> str:
    return await asyncio.to_thread(_summarization.summarize, query, text)
