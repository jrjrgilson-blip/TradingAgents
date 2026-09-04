"""
Streamlit wrapper para o TradingAgents.

Fica no lugar do pacote `cli/`: chama `tradingagents` direto, sem passar
pelo terminal. Rode com:

    streamlit run app.py
"""

import os
from datetime import date

import streamlit as st

st.set_page_config(page_title="TradingAgents", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------
# Chaves e caminhos: definidos ANTES de importar o pacote, porque o
# DEFAULT_CONFIG lê as env vars no momento do import do módulo.
# ---------------------------------------------------------------------------

def _bootstrap_env():
    """Carrega chaves de st.secrets (deploy) ou do ambiente local."""
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "FRED_API_KEY",
    ):
        if key in st.secrets and not os.environ.get(key):
            os.environ[key] = st.secrets[key]

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


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

if "runs" not in st.session_state:
    st.session_state.runs = {}  # chave "TICKER|data" -> {"state":..., "decision":...}


# ---------------------------------------------------------------------------
# Painel lateral
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Configuração")

    api_key = st.text_input(
        "Chave da API",
        type="password",
        value=os.environ.get("OPENAI_API_KEY", ""),
        help="Usada só nesta sessão. Não é gravada em lugar nenhum.",
    )

    provider = st.selectbox(
        "Provedor",
        ["openai", "anthropic", "google", "deepseek", "ollama"],
    )

    deep_model = st.text_input("Modelo de raciocínio", DEFAULT_CONFIG["deep_think_llm"])
    quick_model = st.text_input("Modelo rápido", DEFAULT_CONFIG["quick_think_llm"])

    debate_rounds = st.slider("Rodadas de debate", 1, 4, DEFAULT_CONFIG["max_debate_rounds"])
    risk_rounds = st.slider("Rodadas de risco", 1, 4, DEFAULT_CONFIG["max_risk_discuss_rounds"])

    language = st.selectbox("Idioma dos relatórios", ["Portuguese", "English"])

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

run = st.button("Rodar análise", type="primary", disabled=not (ticker and api_key))


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
    os.environ["OPENAI_API_KEY"] = api_key  # ajuste conforme o provedor

    run_key = f"{ticker}|{analysis_date.isoformat()}"

    with st.status(f"Analisando {ticker}…", expanded=True) as status:
        try:
            st.write("Montando o grafo de agentes")
            graph = TradingAgentsGraph(debug=False, config=build_config())

            st.write("Rodando analistas, debate e comitê de risco")
            state, decision = graph.propagate(ticker, analysis_date.isoformat())

            st.session_state.runs[run_key] = {"state": state, "decision": decision}
            status.update(label=f"{ticker} concluído", state="complete")
        except Exception as exc:
            status.update(label="Falhou", state="error")
            st.exception(exc)


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

run_key = f"{ticker}|{analysis_date.isoformat()}"
result = st.session_state.runs.get(run_key)

if result:
    st.subheader("Decisão")
    st.write(result["decision"])

    state = result["state"]

    # O primeiro retorno de .propagate() é o estado final do grafo.
    # Os nomes das chaves podem mudar entre versões — daí a varredura.
    if isinstance(state, dict):
        report_keys = [k for k in state if "report" in k.lower() or "state" in k.lower()]
        if report_keys:
            st.subheader("Relatórios por agente")
            for key in report_keys:
                with st.expander(key.replace("_", " ")):
                    st.write(state[key])
        with st.expander("Estado bruto"):
            st.json(state, expanded=False)

    st.divider()
    st.subheader("Registrar resultado")
    st.caption(
        "Depois que a posição fechar, informe o retorno realizado. "
        "É isso que alimenta a reflexão usada nas próximas análises."
    )
    returns = st.number_input("Retorno da posição", value=0.0, step=100.0)
    if st.button("Salvar reflexão"):
        try:
            graph = TradingAgentsGraph(debug=False, config=build_config())
            graph.reflect_and_remember(returns)
            st.success("Reflexão registrada no histórico.")
        except Exception as exc:
            st.exception(exc)

if st.session_state.runs:
    with st.sidebar:
        st.divider()
        st.caption("Análises nesta sessão")
        for key in st.session_state.runs:
            st.write(key.replace("|", " · "))
