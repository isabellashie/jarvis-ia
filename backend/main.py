"""
JARVIS Acadêmico — Servidor FastAPI

Endpoints:
  POST /chat                 → Conversa principal com tool calling
  GET  /agenda               → Lista eventos da agenda
  POST /agenda               → Adiciona evento à agenda
  GET  /tasks                → Lista tarefas
  POST /tasks                → Adiciona tarefa
  PUT  /tasks/{id}/complete  → Conclui tarefa
  POST /documents/upload     → Faz upload de documento para RAG
  GET  /documents            → Lista documentos indexados
  POST /rag/reindex          → Reconstrói índice RAG
  POST /learn/exercises      → Gera exercícios sobre um tema
  POST /learn/evaluate       → Avalia resposta de exercício
  GET  /logs                 → Retorna logs de tool calls
  GET  /logs/summary         → Resumo dos logs
  DELETE /logs               → Limpa logs
  GET  /health               → Verificação de saúde
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Garante que o diretório raiz está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import agenda, tasks
from backend.rag import get_rag
from backend import logger_system
from backend.llm_client import processar_mensagem, gerar_exercicios, avaliar_resposta_exercicio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando JARVIS Acadêmico...")
    try:
        rag = get_rag()
        logger.info(f"RAG pronto — {len(rag.chunks)} chunks indexados.")
    except Exception as e:
        logger.error(f"Erro ao inicializar RAG: {e}")
    yield
    logger.info("JARVIS encerrado.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="JARVIS Acadêmico",
    description="Assistente pessoal acadêmico com RAG, tool calling e LLM.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Modelos de request ────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    mensagens: List[Dict[str, str]]
    conversa_id: Optional[str] = None


class EventoRequest(BaseModel):
    titulo: str
    data: str
    horario: str = ""
    tipo: str = "aula"
    descricao: str = ""
    local: str = ""


class TarefaRequest(BaseModel):
    titulo: str
    descricao: str = ""
    prioridade: str = "média"
    prazo: str = ""
    disciplina: str = ""


class ExercicioRequest(BaseModel):
    tema: str
    quantidade: int = 3


class AvaliacaoRequest(BaseModel):
    pergunta: str
    resposta_aluno: str
    tema: str


# ── Endpoints de chat ─────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest) -> Dict[str, Any]:
    """
    Endpoint principal do chat com tool calling.
    Recebe o histórico completo de mensagens e retorna a resposta do assistente.
    """
    if not req.mensagens:
        raise HTTPException(status_code=400, detail="Lista de mensagens vazia.")

    try:
        resultado = processar_mensagem(
            historico=req.mensagens,
            conversa_id=req.conversa_id,
        )
        return resultado
    except Exception as e:
        logger.exception("Erro no endpoint /chat")
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints de agenda ───────────────────────────────────────────────────────

@app.get("/agenda")
async def get_agenda(periodo: str = "hoje") -> Dict[str, Any]:
    return agenda.consultar_agenda(periodo)


@app.post("/agenda")
async def post_agenda(evento: EventoRequest) -> Dict[str, Any]:
    resultado = agenda.adicionar_evento(
        titulo=evento.titulo,
        data=evento.data,
        horario=evento.horario,
        tipo=evento.tipo,
        descricao=evento.descricao,
        local=evento.local,
    )
    if "erro" in resultado:
        raise HTTPException(status_code=400, detail=resultado["erro"])
    return resultado


@app.get("/agenda/todos")
async def get_agenda_todos() -> Dict[str, Any]:
    return agenda.listar_todos_eventos()


@app.delete("/agenda/{evento_id}")
async def delete_evento(evento_id: int) -> Dict[str, Any]:
    resultado = agenda.remover_evento(evento_id)
    if "erro" in resultado:
        raise HTTPException(status_code=404, detail=resultado["erro"])
    return resultado


# ── Endpoints de tarefas ──────────────────────────────────────────────────────

@app.get("/tasks")
async def get_tasks(filtro: str = "pendentes") -> Dict[str, Any]:
    return tasks.listar_tarefas(filtro)


@app.post("/tasks")
async def post_task(tarefa: TarefaRequest) -> Dict[str, Any]:
    return tasks.adicionar_tarefa(
        titulo=tarefa.titulo,
        descricao=tarefa.descricao,
        prioridade=tarefa.prioridade,
        prazo=tarefa.prazo,
        disciplina=tarefa.disciplina,
    )


@app.put("/tasks/{tarefa_id}/complete")
async def complete_task(tarefa_id: int) -> Dict[str, Any]:
    resultado = tasks.concluir_tarefa(tarefa_id)
    if "erro" in resultado:
        raise HTTPException(status_code=404, detail=resultado["erro"])
    return resultado


@app.delete("/tasks/{tarefa_id}")
async def delete_task(tarefa_id: int) -> Dict[str, Any]:
    resultado = tasks.remover_tarefa(tarefa_id)
    if "erro" in resultado:
        raise HTTPException(status_code=404, detail=resultado["erro"])
    return resultado


# ── Endpoints de documentos / RAG ─────────────────────────────────────────────

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Faz upload de um documento (.txt ou .pdf) e o adiciona ao índice RAG."""
    extensoes_validas = {".txt", ".pdf", ".md"}
    ext = os.path.splitext(file.filename or "")[1].lower()

    if ext not in extensoes_validas:
        raise HTTPException(
            status_code=400,
            detail=f"Extensão '{ext}' não suportada. Use: {extensoes_validas}",
        )

    conteudo = await file.read()
    if len(conteudo) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx. 10 MB).")

    try:
        rag = get_rag()
        resultado = rag.adicionar_documento(file.filename, conteudo)
        return resultado
    except Exception as e:
        logger.exception("Erro no upload de documento")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def list_documents() -> Dict[str, Any]:
    rag = get_rag()
    docs = rag.listar_documentos()
    return {"total": len(docs), "documentos": docs}


@app.post("/rag/reindex")
async def reindex_rag() -> Dict[str, Any]:
    try:
        rag = get_rag()
        return rag.reindexar()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints de aprendizado ──────────────────────────────────────────────────

@app.post("/learn/exercises")
async def create_exercises(req: ExercicioRequest) -> Dict[str, Any]:
    """Gera exercícios sobre um tema usando RAG + LLM."""
    try:
        exercicios = gerar_exercicios(tema=req.tema, quantidade=req.quantidade)
        return {"tema": req.tema, "exercicios": exercicios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn/evaluate")
async def evaluate_answer(req: AvaliacaoRequest) -> Dict[str, Any]:
    """Avalia a resposta de um estudante a um exercício."""
    try:
        feedback = avaliar_resposta_exercicio(
            pergunta=req.pergunta,
            resposta_aluno=req.resposta_aluno,
            tema=req.tema,
        )
        return {"feedback": feedback}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints de logs ─────────────────────────────────────────────────────────

@app.get("/logs")
async def get_logs(
    limite: int = 50,
    ferramenta: Optional[str] = None,
    conversa_id: Optional[str] = None,
) -> Dict[str, Any]:
    registros = logger_system.obter_logs(
        limite=limite,
        ferramenta_filtro=ferramenta,
        conversa_id_filtro=conversa_id,
    )
    return {"total": len(registros), "logs": registros}


@app.get("/logs/summary")
async def get_logs_summary() -> Dict[str, Any]:
    return logger_system.resumo_logs()


@app.delete("/logs")
async def clear_logs() -> Dict[str, Any]:
    return logger_system.limpar_logs()


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> Dict[str, Any]:
    rag = get_rag()
    return {
        "status": "ok",
        "chunks_indexados": len(rag.chunks),
        "documentos": len(rag.listar_documentos()),
    }


# ── Servir frontend estático ──────────────────────────────────────────────────

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
