"""
Streamlit wrapper para o TradingAgents.

Colocar na raiz do repositório, no mesmo nível de main.py e da pasta
tradingagents/. Rodar com:

    streamlit run app.py
"""

import os
import traceback
from datetime import date

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

            st.session_state.runs[run_key] = {"state": state, "decision": decision}
            st.session_state.last_key = run_key
            status.update(label=f"{ticker} concluído", state="complete")
        except Exception as exc:
            status.update(label="Falhou", state="error")
            st.error(f"{type(exc).__name__}: {exc}")
            st.code(traceback.format_exc())


# ---------------------------------------------------------------------------
# Resultado
#
# Mostra sempre a última análise concluída, e não a que corresponde aos
# campos atuais. Mexer no ticker ou na data depois de rodar não faz mais
# o resultado sumir da tela.
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

    # O primeiro retorno de .propagate() é o estado final do grafo.
    # Os nomes das chaves variam entre versões — daí a varredura.
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

    # -----------------------------------------------------------------------
    # Reflexão
    # -----------------------------------------------------------------------

    st.divider()
    st.subheader("Registrar resultado")
    st.caption(
        "Depois que a posição fechar, informe o retorno realizado. "
        "É isso que alimenta a reflexão usada nas próximas análises."
    )
    returns = st.number_input("Retorno da posição", value=0.0, step=100.0)
    if st.button("Salvar reflexão"):
        try:
            graph = TradingAgentsGraph(debug=debug_mode, config=build_config())
            graph.reflect_and_remember(returns)
            st.success("Reflexão registrada no histórico.")
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")
            st.code(traceback.format_exc())

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
