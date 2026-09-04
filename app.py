"""
Streamlit wrapper para o TradingAgents.

Colocar na raiz do repositório, no mesmo nível de main.py e da pasta
tradingagents/. Rodar com:

    streamlit run app.py
"""

import os
import traceback
from datetime import date, datetime

import streamlit as st

st.set_page_config(page_title="TradingAgents", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# Chaves e caminhos: definidos ANTES de importar o pacote, porque o
# DEFAULT_CONFIG lê as env vars no momento do import do módulo.
# ---------------------------------------------------------------------------

ENV_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "ollama": None,  # local, sem chave
}


def _bootstrap_env():
    """Carrega chaves de st.secrets (se existirem) e fixa caminhos de dados."""
    try:
        secrets = st.secrets
    except Exception:
        secrets = {}

    for key in list(ENV_BY_PROVIDER.values()) + ["FRED_API_KEY"]:
        if key and key in secrets and not os.environ.get(key):
            os.environ[key] = secrets[key]

    # Disco no Streamlit Cloud é efêmero. Aponte para algo persistente
    # se quiser manter o histórico de decisões entre reinícios.
    os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", "./.ta/logs")
    os.environ.setdefault("TRADINGAGENTS_CACHE_DIR", "./.ta/cache")
    os.environ.setdefault(
        "TRADINGAGENTS_MEMORY_LOG_PATH", "./.ta/memory/trading_memory.md"
    )


_bootstrap_env()

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402

try:
    from report_docx import markdown_to_docx
except Exception:  # python-docx ausente ou módulo não encontrado
    markdown_to_docx = None


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

if "runs" not in st.session_state:
    st.session_state.runs = {}     # "TICKER|data" -> {"state":..., "decision":...}
if "last_key" not in st.session_state:
    st.session_state.last_key = None   # última análise concluída


# ---------------------------------------------------------------------------
# Painel lateral
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Configuração")

    provider = st.selectbox(
        "Provedor",
        list(ENV_BY_PROVIDER.keys()),
    )

    env_var = ENV_BY_PROVIDER[provider]

    if env_var:
        api_key = st.text_input(
            f"Chave ({env_var})",
            type="password",
            value=os.environ.get(env_var, ""),
            help="Usada só nesta sessão. Não é gravada em lugar nenhum.",
        )
    else:
        api_key = ""
        st.caption("Ollama roda local, sem chave.")

    deep_model = st.text_input("Modelo de raciocínio", DEFAULT_CONFIG["deep_think_llm"])
    quick_model = st.text_input("Modelo rápido", DEFAULT_CONFIG["quick_think_llm"])

    debate_rounds = st.slider("Rodadas de debate", 1, 4, DEFAULT_CONFIG["max_debate_rounds"])
    risk_rounds = st.slider("Rodadas de risco", 1, 4, DEFAULT_CONFIG["max_risk_discuss_rounds"])

    language = st.selectbox("Idioma dos relatórios", ["Portuguese", "English"])

    debug_mode = st.checkbox(
        "Modo debug",
        value=True,
        help="Imprime o progresso no terminal onde você rodou o streamlit.",
    )

    st.divider()
    st.caption(
        "Cada análise dispara dezenas de chamadas de LLM. "
        "Mais rodadas multiplicam o custo."
    )


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

st.title("TradingAgents")

col_a, col_b, col_c = st.columns([2, 2, 3])

with col_a:
    ticker = st.text_input("Ticker", "PETR4.SA").strip().upper()

with col_b:
    analysis_date = st.date_input("Data da análise", date.today())

with col_c:
    # O benchmark_map do projeto não cobre ".SA" — sem isso, papel
    # brasileiro cai no default "" e o alfa sai calculado contra o SPY.
    default_bench = "^BVSP" if ticker.endswith(".SA") else ""
    benchmark = st.text_input(
        "Benchmark para o alfa",
        default_bench,
        help="Deixe vazio para o projeto escolher pelo sufixo do ticker.",
    ).strip()

can_run = bool(ticker) and (bool(api_key) or provider == "ollama")
run = st.button("Rodar análise", type="primary", disabled=not can_run)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def build_config():
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model
    config["max_debate_rounds"] = debate_rounds
    config["max_risk_discuss_rounds"] = risk_rounds
    config["output_language"] = language
    if benchmark:
        config["benchmark_ticker"] = benchmark
    return config


if run:
    if env_var and api_key:
        os.environ[env_var] = api_key

    run_key = f"{ticker}|{analysis_date.isoformat()}"

    with st.status(f"Analisando {ticker}…", expanded=True) as status:
        try:
            st.write("Montando o grafo de agentes")
            graph = TradingAgentsGraph(debug=debug_mode, config=build_config())

            st.write("Rodando analistas, debate e comitê de risco")
            state, decision = graph.propagate(ticker, analysis_date.isoformat())

            st.session_state.runs[run_key] = {
                "state": state,
                "decision": decision,
                "provider": provider,
                "deep_model": deep_model,
                "quick_model": quick_model,
                "benchmark": benchmark,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
            st.session_state.last_key = run_key
            status.update(label=f"{ticker} concluído", state="complete")
        except Exception as exc:
            status.update(label="Falhou", state="error")
            st.error(f"{type(exc).__name__}: {exc}")
            st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Montagem do relatório em markdown
# ---------------------------------------------------------------------------

def build_markdown(key, result):
    ticker_part, date_part = key.split("|")
    lines = [
        f"# TradingAgents — {ticker_part}",
        "",
        f"- Data da análise: {date_part}",
        f"- Gerado em: {result.get('finished_at', '')}",
        f"- Provedor: {result.get('provider', '')}",
        f"- Modelo de raciocínio: {result.get('deep_model', '')}",
        f"- Modelo rápido: {result.get('quick_model', '')}",
    ]
    if result.get("benchmark"):
        lines.append(f"- Benchmark: {result['benchmark']}")

    lines += ["", "---", "", "## Decisão final", "", str(result.get("decision", "")), ""]

    state = result.get("state")
    if isinstance(state, dict):
        for k, v in state.items():
            if isinstance(v, str) and v.strip():
                title = k.replace("_", " ").strip().capitalize()
                lines += ["---", "", f"## {title}", "", v, ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resultado
#
# Mostra sempre a última análise concluída, e não a que corresponde aos
# campos atuais. Mexer no ticker ou na data depois de rodar não faz o
# resultado sumir da tela.
# ---------------------------------------------------------------------------

if st.session_state.runs:
    keys = list(st.session_state.runs.keys())
    default_index = keys.index(st.session_state.last_key) if st.session_state.last_key in keys else 0

    st.divider()
    selected = st.selectbox(
        "Análise",
        keys,
        index=default_index,
        format_func=lambda k: k.replace("|", "  ·  "),
    )

    result = st.session_state.runs[selected]
    decision = result["decision"]
    state = result["state"]

    # Download ----------------------------------------------------------------
    markdown = build_markdown(selected, result)
    tk, dt = selected.split("|")
    base_name = f"tradingagents_{tk.replace('.', '_')}_{dt}"

    col_md, col_doc = st.columns(2)
    with col_md:
        st.download_button(
            "Baixar em Markdown (.md)",
            data=markdown.encode("utf-8"),
            file_name=f"{base_name}.md",
            mime="text/markdown",
        )
    with col_doc:
        if markdown_to_docx is None:
            st.button("Baixar em Word (.docx)", disabled=True)
            st.caption("Requer python-docx e o arquivo report_docx.py na raiz.")
        else:
            try:
                docx_bytes = markdown_to_docx(markdown)
                st.download_button(
                    "Baixar em Word (.docx)",
                    data=docx_bytes,
                    file_name=f"{base_name}.docx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                    type="primary",
                )
            except Exception as exc:
                st.button("Baixar em Word (.docx)", disabled=True)
                st.caption(f"Falha ao montar o documento: {exc}")

    st.caption(
        "O Word sai formatado com capa, sumário, cabeçalho e numeração. "
        "O Markdown é o texto cru, para editar ou arquivar em texto."
    )

    # Decisão -----------------------------------------------------------------
    st.subheader("Decisão")
    if decision is None or (isinstance(decision, str) and not decision.strip()):
        st.warning("A execução terminou sem produzir uma decisão legível.")
    elif isinstance(decision, str):
        st.markdown(decision)
    elif isinstance(decision, dict):
        st.json(decision)
    else:
        st.write(decision)
        st.caption(f"Tipo retornado: {type(decision).__name__}")

    # Relatórios --------------------------------------------------------------
    if isinstance(state, dict):
        text_keys = [
            k for k, v in state.items()
            if isinstance(v, str) and v.strip() and k != "decision"
        ]
        if text_keys:
            st.subheader("Relatórios por agente")
            for key in text_keys:
                with st.expander(key.replace("_", " ")):
                    st.markdown(state[key])

        other_keys = [k for k in state if k not in text_keys]
        if other_keys:
            with st.expander("Demais campos do estado"):
                st.write({k: state[k] for k in other_keys})
    elif state is not None:
        with st.expander("Estado retornado"):
            st.write(state)
            st.caption(f"Tipo: {type(state).__name__}")

    # Reflexão ----------------------------------------------------------------
    # O nome do método mudou entre versões (o main.py ainda cita
    # reflect_and_remember, que não existe mais em 0.4.0). Procura os
    # candidatos conhecidos e mostra o que a classe realmente oferece.
    st.divider()
    st.subheader("Registrar resultado")

    REFLECT_CANDIDATES = (
        "reflect_and_remember",
        "reflect",
        "reflect_on_decision",
        "remember",
        "update_memory",
    )
    available = [m for m in REFLECT_CANDIDATES if hasattr(TradingAgentsGraph, m)]

    if available:
        st.caption(
            "Depois que a posição fechar, informe o retorno realizado. "
            "É isso que alimenta a reflexão usada nas próximas análises."
        )
        method_name = available[0] if len(available) == 1 else st.selectbox(
            "Método", available
        )
        returns = st.number_input("Retorno da posição", value=0.0, step=100.0)
        if st.button("Salvar reflexão"):
            try:
                graph = TradingAgentsGraph(debug=debug_mode, config=build_config())
                getattr(graph, method_name)(returns)
                st.success("Reflexão registrada no histórico.")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")
                st.code(traceback.format_exc())
    else:
        st.info(
            "Esta versão do TradingAgents não expõe um método público de reflexão. "
            "O registro de decisões roda sozinho ao final de cada análise, "
            "gravado em "
            f"`{os.environ.get('TRADINGAGENTS_MEMORY_LOG_PATH')}`."
        )
        with st.expander("Métodos públicos disponíveis na classe"):
            st.write([m for m in dir(TradingAgentsGraph) if not m.startswith("_")])

else:
    st.info("Configure o provedor na barra lateral e rode uma análise.")


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------

with st.expander("Diagnóstico"):
    st.write("Análises em memória:", list(st.session_state.runs.keys()))
    st.write("Última concluída:", st.session_state.last_key)
    st.write("Provedor:", provider, "· variável:", env_var)
    st.write("Chave presente no ambiente:", bool(env_var and os.environ.get(env_var)))
    st.write("Caminho da memória:", os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH"))
