# 🤖 JARVIS Acadêmico

> **Assistente pessoal inteligente para estudantes** — combina RAG, Tool Calling e LLM (Gemma 12B) para apoiar o aprendizado e organização acadêmica.

---

## 🎯 Sobre o Projeto

O JARVIS Acadêmico está desenvolvido como trabalho prático da disciplina de Inteligência Artificial. O sistema integra três pilares técnicos modernos:

| Pilar | Tecnologia | Função |
|---|---|---|
| **RAG** | sentence-transformers + NumPy | Recuperação de trechos relevantes de materiais de estudo |
| **Tool Calling** | Gemma 12B via prompt engineering | LLM decide qual ferramenta usar para cada pergunta |
| **LLM** | Gemma 3 12B (via llm.liaufms.org) | Geração de respostas, exercícios e avaliações |

---

## 🚀 Instalação e Execução

### Pré-requisitos

- Python 3.10+
- pip

### 1. Clone o repositório

```bash
git clone <github.com/isabellashie/jarvis-ia>
cd jarvis
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

> A primeira execução baixará o modelo de embeddings (~120 MB). Isso ocorre automaticamente.

### 3. Inicie o servidor

```bash
# A partir da raiz do projeto:
python -m backend.main
```

Ou com uvicorn diretamente:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Acesse o JARVIS

Abra no navegador: **http://localhost:8000**

A interface do chat abrirá automaticamente (o backend serve o frontend estático).

---

## 📁 Estrutura do Projeto

```
jarvis/
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI — rotas e lifespan
│   ├── llm_client.py    # Cliente Gemma 12B + orquestrador de tool calling
│   ├── rag.py           # Pipeline RAG completo (indexação + busca)
│   ├── tools.py         # Definição e execução das 7 ferramentas
│   ├── agenda.py        # CRUD de eventos da agenda (JSON)
│   ├── tasks.py         # CRUD de tarefas acadêmicas (JSON)
│   └── logger_system.py # Logging de tool calls em JSONL
│
├── frontend/
│   ├── index.html       # Interface JARVIS
│   ├── style.css        # Estilos
│   └── app.js           # Lógica do frontend (chat, agenda, tarefas, docs)
│
├── data/
│   ├── documents/       # Dataset: 10 documentos da FACOM/UFMS em .txt
│   │   ├── 01_introducao_a_ia.txt
│   │   ├── 02_knn.txt
│   │   ├── 03_arvores_de_decisao.txt
│   │   ├── 04_sistemas_numeracao.txt
│   │   ├── 05_operacoes_aritmeticas_overflow.txt
│   │   ├── 06_engenharia_de_requisitos.txt
│   │   ├── 07_modelagem_uml_casos_de_uso.txt
│   │   ├── 08_apsoo_orientacao_objetos.txt
│   │   ├── 09_java_web_spring_boot.txt
│   │   └── 10_exercicios_resolvidos_ia.txt
│   ├── agenda.json      # Dados da agenda (persistência local)
│   ├── tasks.json       # Dados das tarefas (persistência local)
│   └── rag_index.pkl    # Índice vetorial (gerado automaticamente)
│
├── logs/
│   └── tool_calls.jsonl # Registro de chamadas de ferramentas
│
├── requirements.txt
└── README.md
```

---

## 🔧 Funcionalidades (Entrega 1)

### 3.1 Consulta a Materiais de Estudo (RAG)

O pipeline RAG implementado:

1. **Carregamento**: lê `.txt` e `.pdf` do diretório `data/documents/`
2. **Chunking**: divide por parágrafos com overlap de 40 palavras (~300 palavras por chunk)
3. **Embeddings**: modelo `paraphrase-multilingual-MiniLM-L12-v2` (suporta português)
4. **Indexação**: índice vetorial em pickle (recarregado no startup)
5. **Busca**: similaridade de cosseno com NumPy — top-4 chunks por padrão
6. **Geração**: contexto recuperado + pergunta → Gemma 12B → resposta

**Exemplos de uso:**
- _"Explique regressão logística"_
- _"O que é IA?"_
- _"Como funciona o mecanismo de atenção?"_

### 3.2 Agenda Acadêmica

Gerenciamento via JSON com suporte a:
- Consulta por período: `hoje`, `amanhã`, `semana`, ou data específica
- Tipos de evento: aula, prova, trabalho, seminário, reunião
- Interface visual com filtros rápidos

**Exemplos de uso:**
- _"O que tenho na agenda hoje?"_
- _"Tenho prova essa semana?"_
- _"Quais são minhas aulas amanhã?"_

### 3.3 Lista de Tarefas

CRUD completo com:
- Adicionar tarefa com prioridade, prazo e disciplina
- Listar com filtros (pendentes, concluídas, por prioridade)
- Marcar como concluída

**Exemplos de uso:**
- _"Quais tarefas estão pendentes?"_
- _"Adicione uma tarefa de estudar machine learning com prioridade alta"_
- _"Marque a tarefa 2 como concluída"_

---

## 🛠️ Tool Calling

O sistema implementa **7 ferramentas** cujas chamadas são decididas pelo Gemma 12B via system prompt estruturado:

| # | Ferramenta | Descrição |
|---|---|---|
| 1 | `consultar_agenda` | Busca eventos por período |
| 2 | `adicionar_evento_agenda` | Registra novo evento |
| 3 | `listar_tarefas` | Lista tarefas com filtro |
| 4 | `adicionar_tarefa` | Cria nova tarefa |
| 5 | `concluir_tarefa` | Marca tarefa como feita |
| 6 | `buscar_material_rag` | Pesquisa nos documentos indexados |
| 7 | `reindexar_documentos` | Reconstrói o índice RAG |

**Formato de tool call** (via prompt engineering com parser de regex):

```xml
<tool_call>
{"name": "consultar_agenda", "arguments": {"periodo": "hoje"}}
</tool_call>
```

**Logs registrados** em `logs/tool_calls.jsonl`:
```json
{
  "timestamp": "2024-06-01T14:23:11",
  "ferramenta": "buscar_material_rag",
  "entrada": {"query": "embeddings", "top_k": 4},
  "saida": {"trechos_encontrados": 4, "trechos": [...]},
  "duracao_ms": 87.3,
  "status": "sucesso"
}
```

---

## 🧠 Funcionalidades de Aprendizado

### 1. Gerador de Exercícios (Tab "Aprendizado")

- Digita um tema → JARVIS busca no RAG + gera exercícios com Gemma 12B
- Suporta múltipla escolha e questões dissertativas
- Inclui gabarito com explicação

### 2. Active Recall com Avaliação Interativa

- O estudante responde uma pergunta gerada
- O JARVIS avalia a resposta consultando o material de referência
- Retorna feedback construtivo com nota e pontos de melhoria

---

## 📊 Dataset

O dataset foi montado para refletir o uso real do JARVIS por estudantes da **FACOM/UFMS** (Faculdade de Computação da Universidade Federal de Mato Grosso do Sul). Em vez de textos sintéticos, todos os documentos são adaptações de materiais didáticos efetivamente utilizados em disciplinas do curso.

### Origem dos Dados

Os 10 documentos foram derivados de slides, notas de aula e listas de exercícios das seguintes disciplinas da FACOM/UFMS:

| Disciplina | Documento(s) | Professor de referência |
|---|---|---|
| Inteligência Artificial | `01`, `02`, `03`, `10` | Prof. Edson Takashi Matsubara (FACOM/UFMS) |
| Organização de Computadores | `04`, `05` | Material da disciplina |
| Engenharia de Requisitos | `06`, `07` | Prof. Me. Daniel Cunha da Silva (UFMS) |
| Análise e Projeto OO (APSOO) | `08` | Material da disciplina |
| Programação Web | `09` | Material da disciplina |

Bibliografia citada nos materiais originais inclui: Sommerville (2016), Wiegers & Beatty (2013), Russell & Norvig, Jacobson et al. (1993), Rumbaugh et al. (1999), Valente (2020), entre outros.

### Tipo de Conteúdo

Os documentos cobrem dois grandes domínios complementares:

**Bloco 1 — Inteligência Artificial e Machine Learning (4 documentos)**
**Bloco 2 — Engenharia de Software, Organização de Computadores e Web (6 documentos)**

A escolha de cobrir disciplinas variadas (não apenas IA) é intencional: o JARVIS é um assistente acadêmico geral, e o dataset reflete a diversidade de matérias que um estudante de Computação consulta no dia a dia. Isso permite testar a robustez da recuperação semântica em domínios distintos com vocabulários técnicos diferentes.

**Estatísticas do dataset:**
- 10 documentos `.txt` em português
- ~11.000 palavras totais
- ~80 KB de texto puro
- Média de ~1.100 palavras por documento
- Estrutura semântica preservada (módulos, seções numeradas, listas)

### Limitações do Dataset

É importante reconhecer as limitações dos dados utilizados:

1. **Cobertura parcial das disciplinas**: cada documento sintetiza tópicos selecionados, não a ementa completa. Perguntas muito específicas sobre subtópicos não cobertos terão recuperação fraca.

2. **Idioma único**: todos os documentos estão em português brasileiro. Buscas em inglês podem ter qualidade reduzida apesar do modelo de embeddings ser multilíngue.

3. **Fórmulas em texto puro**: equações foram transcritas como texto plano (ex: `σ(z) = 1 / (1 + e^(-z))`), sem suporte a LaTeX nem renderização matemática. Isso pode afetar a busca por conceitos quando a pergunta usa notação simbólica.

4. **Ausência de diagramas**: os materiais originais incluem figuras, fluxogramas e diagramas UML que não estão presentes no dataset textual. Perguntas sobre "como é o diagrama X" são respondidas apenas com descrição textual.

5. **Atualização estática**: o dataset reflete o conteúdo das aulas no momento da coleta. Novas versões de tecnologias (ex: Spring Boot 4, novos algoritmos) não estarão presentes.

6. **Vieses pedagógicos**: por serem materiais didáticos introdutórios, há simplificações conceituais que estudantes avançados podem notar como incompletas.

### Entrega do Dataset

Os documentos estão disponíveis na pasta **`/data/documents`** do repositório, em arquivos `.txt` UTF-8 individuais. Não há dependência de serviços externos — o dataset é totalmente local e versionado junto com o código.

### Estratégia de Chunking

A divisão dos documentos em chunks é uma das decisões mais impactantes do pipeline RAG. Adotamos a seguinte estratégia (implementada em `backend/rag.py`):

- **Critério de quebra**: divisão por **parágrafos** (separador `\n\n`), respeitando as unidades semânticas naturais do texto.
- **Tamanho alvo**: ~**300 palavras** por chunk.
- **Overlap**: **40 palavras** de sobreposição entre chunks consecutivos.
- **Acumulação**: parágrafos pequenos são agregados ao chunk corrente até atingir o limite; parágrafos grandes podem gerar um único chunk maior sem fragmentação interna.

O algoritmo está em `_chunk_texto()` no módulo `rag.py`:

```
1. Divide o texto em parágrafos (split por \n\n).
2. Para cada parágrafo:
   - Se adicionar ao buffer atual ultrapassa 300 palavras E o buffer não está vazio,
     fecha o chunk atual.
   - Mantém as últimas 40 palavras como overlap para o próximo chunk.
3. Acumula o parágrafo no buffer.
4. No final, salva o buffer restante como último chunk.
```

### Impacto no RAG

Cada decisão da estratégia de chunking afeta diretamente o desempenho do RAG. Abaixo, o trade-off de cada parâmetro escolhido:

**Por que dividir por parágrafos (e não por tokens fixos)?**
- ✅ **Coesão temática**: parágrafos costumam expressar uma ideia completa. Embeddings de chunks coesos têm vetores mais discriminativos, melhorando a relevância da busca.
- ✅ **Aderência à estrutura dos materiais**: nossos documentos são fortemente estruturados (Módulo X, seção Y), e o parágrafo é a unidade natural dessa estrutura.
- ⚠️ **Trade-off**: parágrafos muito desiguais geram chunks de tamanhos variáveis, o que pode reduzir a uniformidade da recuperação.

**Por que ~300 palavras por chunk?**
- ✅ **Densidade semântica**: tamanho suficiente para conter uma ideia completa com contexto, mas pequeno o bastante para que o embedding não fique "diluído" em muitos tópicos.
- ✅ **Custo de tokens**: ao injetar top-4 chunks no prompt do Gemma 12B, ficamos em ~1.200 palavras de contexto, deixando espaço para histórico de conversa.
- ⚠️ **Trade-off**: chunks pequenos demais perdem contexto; chunks grandes demais introduzem ruído na busca.

**Por que overlap de 40 palavras?**
- ✅ **Recuperação de fronteira**: garante que conceitos definidos no fim de um parágrafo e usados no início do próximo possam ser recuperados juntos.
- ✅ **Robustez a paráfrases**: se a pergunta usar termos da fronteira entre dois chunks, ainda há chance de recuperar o trecho relevante.
- ⚠️ **Trade-off**: overlap aumenta o número total de chunks (e o custo de indexação) sem aumentar a informação única.

**Métricas observadas no dataset atual:**
- Os 10 documentos geram aproximadamente 35–45 chunks após processamento (variação devido aos parágrafos heterogêneos).
- O índice vetorial completo ocupa ~150 KB em pickle (chunks + embeddings de 384 dimensões).
- Tempo médio de busca por consulta: < 20 ms (similaridade de cosseno em NumPy).

**Alternativas consideradas e descartadas:**
- _Sentence chunking_: chunks muito pequenos (1–3 sentenças) fragmentavam conceitos e geravam respostas incoerentes.
- _Fixed-token chunking: quebrava parágrafos no meio, prejudicando a coesão e gerando embeddings menos discriminativos.
- _Semantic chunking_: exigiria modelo de embeddings adicional para identificar quebras semânticas, aumentando complexidade sem ganho significativo para o tamanho do nosso dataset.

---

## 🤖 IAs Utilizadas no Desenvolvimento

| Ferramenta | Uso |
|---|---|
| **Claude (Anthropic)** | Arquitetura geral, auxílio na documentação e refinamento estrutural do projeto |
| **Claude Code** | Desenvolvimento e refinamento visual do frontend, especialmente estilização CSS e ajustes da interface |
| **Gemini (Google)** | Padronização e refinamento dos documentos utilizados no RAG para melhorar consistência e recuperação semântica |
| **Gemma 3 12B** | LLM central do sistema (inferência em tempo de execução) |

---

## ⚠️ Limitações Conhecidas

1. **Índice em memória**: o índice RAG é armazenado em pickle; não é adequado para escala com milhares de documentos
2. **Tool calling por prompt**: o Gemma pode ocasionalmente não seguir o formato `<tool_call>` exatamente
3. **Sem autenticação**: o sistema não tem controle de acesso (adequado apenas para uso local)
4. **Memória de contexto**: conversas muito longas podem exceder a janela de contexto do Gemma
5. **Idioma**: o modelo de embeddings é multilingual mas foi otimizado principalmente para inglês

---

## 👥 Equipe

- **Integrante 1**: _[Giovanna dos Santos Dalcin - RGA: 202419070531]_
- **Integrante 2**: _[Isabella de Carvalho Shie - RGA: 202419070299]_

**Disciplina**: Inteligência Artificial  
**Professor**: _[Edson Takashi Matsubara]_  
**Entrega**: Trabalho 1 — Funcionalidades 3.1, 3.2, 3.3
