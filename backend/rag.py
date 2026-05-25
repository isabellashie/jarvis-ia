"""
Pipeline de RAG (Retrieval-Augmented Generation).

Fluxo:
  1. Carregamento de documentos (.txt e .pdf)
  2. Chunking por parágrafo com overlap
  3. Geração de embeddings (sentence-transformers multilingual)
  4. Armazenamento em índice local (pickle)
  5. Recuperação por similaridade de cosseno
"""

import os
import pickle
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "documents")
INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rag_index.pkl")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


# ── Chunking ────────────────────────────────────────────────────────────────

def _chunk_texto(
    texto: str,
    chunk_palavras: int = 300,
    overlap_palavras: int = 40,
) -> List[str]:
    """
    Divide o texto em chunks de tamanho aproximado por palavras.
    Tenta respeitar quebras de parágrafo e usa overlap para manter contexto.
    """
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks: List[str] = []
    buffer: List[str] = []
    tamanho_buffer = 0

    for para in paragrafos:
        palavras = para.split()
        if tamanho_buffer + len(palavras) > chunk_palavras and buffer:
            chunks.append(" ".join(buffer))
            # overlap: mantém últimas N palavras
            overlap = buffer[-overlap_palavras:] if overlap_palavras < len(buffer) else buffer[:]
            buffer = overlap
            tamanho_buffer = len(buffer)
        buffer.extend(palavras)
        tamanho_buffer += len(palavras)

    if buffer:
        chunks.append(" ".join(buffer))

    return chunks


# ── Carregamento de documentos ──────────────────────────────────────────────

def _carregar_txt(caminho: Path) -> str:
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _carregar_pdf(caminho: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(caminho) as pdf:
            paginas = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(paginas)
    except ImportError:
        logger.warning("pdfplumber não instalado. PDFs serão ignorados.")
        return ""
    except Exception as e:
        logger.error(f"Erro ao ler PDF {caminho}: {e}")
        return ""


def carregar_documentos(docs_dir: str = DOCS_DIR) -> List[Dict[str, Any]]:
    """Carrega todos os documentos do diretório e retorna lista de chunks."""
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.warning(f"Diretório de documentos não encontrado: {docs_dir}")
        return []

    chunks_resultado: List[Dict[str, Any]] = []

    for arquivo in sorted(docs_path.iterdir()):
        if arquivo.suffix.lower() == ".txt":
            texto = _carregar_txt(arquivo)
        elif arquivo.suffix.lower() == ".pdf":
            texto = _carregar_pdf(arquivo)
        else:
            continue

        if not texto.strip():
            continue

        chunks = _chunk_texto(texto)
        for idx, chunk in enumerate(chunks):
            chunks_resultado.append({
                "source": arquivo.name,
                "chunk_id": idx,
                "content": chunk,
            })
        logger.info(f"Documento '{arquivo.name}' → {len(chunks)} chunks")

    logger.info(f"Total de chunks gerados: {len(chunks_resultado)}")
    return chunks_resultado


# ── Índice vetorial ─────────────────────────────────────────────────────────

class RAGPipeline:
    """
    Pipeline completo de RAG com suporte a reindexação dinâmica e upload de novos documentos.
    """

    def __init__(
        self,
        docs_dir: str = DOCS_DIR,
        index_path: str = INDEX_PATH,
        model_name: str = MODEL_NAME,
    ):
        self.docs_dir = docs_dir
        self.index_path = index_path
        self.model_name = model_name
        self._model = None
        self.chunks: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        self._inicializar()

    # ── Modelo ──────────────────────────────────────────────────────────────

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Carregando modelo de embeddings: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    # ── Índice ──────────────────────────────────────────────────────────────

    def _inicializar(self) -> None:
        if os.path.exists(self.index_path):
            self._carregar_indice()
        else:
            self.reindexar()

    def _carregar_indice(self) -> None:
        try:
            with open(self.index_path, "rb") as f:
                dados = pickle.load(f)
            self.chunks = dados["chunks"]
            self.embeddings = dados["embeddings"]
            logger.info(f"Índice RAG carregado: {len(self.chunks)} chunks")
        except Exception as e:
            logger.error(f"Falha ao carregar índice: {e}. Reindexando...")
            self.reindexar()

    def _salvar_indice(self) -> None:
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, "wb") as f:
            pickle.dump({"chunks": self.chunks, "embeddings": self.embeddings}, f)
        logger.info("Índice RAG salvo.")

    def reindexar(self) -> Dict[str, Any]:
        """Reconstrói o índice a partir dos documentos no diretório."""
        self.chunks = carregar_documentos(self.docs_dir)
        if not self.chunks:
            self.embeddings = np.array([])
            logger.warning("Nenhum documento encontrado para indexar.")
            return {"chunks_indexados": 0}

        textos = [c["content"] for c in self.chunks]
        logger.info(f"Gerando embeddings para {len(textos)} chunks...")
        self.embeddings = self.model.encode(textos, show_progress_bar=False, batch_size=32)
        self._salvar_indice()
        return {"chunks_indexados": len(self.chunks)}

    # ── Upload de novo documento ─────────────────────────────────────────────

    def adicionar_documento(self, nome_arquivo: str, conteudo: bytes) -> Dict[str, Any]:
        """Salva um novo documento e atualiza o índice incrementalmente."""
        os.makedirs(self.docs_dir, exist_ok=True)
        caminho = Path(self.docs_dir) / nome_arquivo

        with open(caminho, "wb") as f:
            f.write(conteudo)

        # Determina texto
        if nome_arquivo.lower().endswith(".pdf"):
            texto = _carregar_pdf(caminho)
        else:
            texto = conteudo.decode("utf-8", errors="replace")

        novos_chunks = _chunk_texto(texto)
        novos_docs = [
            {"source": nome_arquivo, "chunk_id": i, "content": c}
            for i, c in enumerate(novos_chunks)
        ]

        if novos_docs:
            novos_embs = self.model.encode(
                [d["content"] for d in novos_docs], show_progress_bar=False
            )
            self.chunks.extend(novos_docs)
            if self.embeddings is not None and len(self.embeddings) > 0:
                self.embeddings = np.vstack([self.embeddings, novos_embs])
            else:
                self.embeddings = novos_embs
            self._salvar_indice()

        return {
            "arquivo": nome_arquivo,
            "novos_chunks": len(novos_docs),
            "total_chunks": len(self.chunks),
        }

    def listar_documentos(self) -> List[str]:
        """Retorna lista de fontes únicas no índice."""
        return list({c["source"] for c in self.chunks})

    # ── Busca ────────────────────────────────────────────────────────────────

    def buscar(self, query: str, top_k: int = 4, score_minimo: float = 0.2) -> List[Dict[str, Any]]:
        """
        Recupera os chunks mais relevantes para a query usando similaridade de cosseno.

        Args:
            query: Pergunta ou termo de busca.
            top_k: Número máximo de resultados.
            score_minimo: Similaridade mínima para incluir o chunk.

        Returns:
            Lista de dicionários com 'source', 'content' e 'score'.
        """
        if not self.chunks or self.embeddings is None or len(self.embeddings) == 0:
            return []

        query_emb = self.model.encode([query])[0]

        norma_docs = np.linalg.norm(self.embeddings, axis=1) + 1e-8
        norma_query = np.linalg.norm(query_emb) + 1e-8
        scores = (self.embeddings @ query_emb) / (norma_docs * norma_query)

        indices_top = np.argsort(scores)[::-1][:top_k]

        resultados = []
        for idx in indices_top:
            score = float(scores[idx])
            if score < score_minimo:
                continue
            resultados.append({
                "source": self.chunks[idx]["source"],
                "chunk_id": self.chunks[idx]["chunk_id"],
                "content": self.chunks[idx]["content"],
                "score": round(score, 4),
            })

        return resultados


# ── Instância global ─────────────────────────────────────────────────────────
_rag_instance: Optional[RAGPipeline] = None


def get_rag() -> RAGPipeline:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGPipeline()
    return _rag_instance
