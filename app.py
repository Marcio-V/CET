# app.py
"""
Comparador: Financiamento Imobiliário x Consórcio — CET, VPL, Fluxos e Amortização
Instruções:
    pip install streamlit numpy pandas altair
    streamlit run app.py

Observações:
- Cálculos são aproximações pedagógicas para comparação entre cenários.
- Formatação numérica em estilo BR: ponto para milhar e vírgula para decimais.
"""

import streamlit as st
import numpy as np
import pandas as pd
import altair as alt

# -----------------------------
# Helpers: formatação (BR) e financeiras
# -----------------------------
def br_currency(x):
    """Formata número em real no padrão BR: 1.234.567,89"""
    try:
        s = f"{x:,.2f}"
        # troca separadores: 1,234,567.89 -> 1.234.567,89
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except Exception:
        return f"R$ {x}"

def br_percent(x, decimals=2):
    """Formata número percentual (x em %) como '12,34%'"""
    try:
        s = f"{x:.{decimals}f}"
        s = s.replace(".", ",")
        return f"{s}%"
    except Exception:
        return f"{x}%"

def annuity_payment(principal: float, monthly_rate: float, months: int) -> float:
    """Parcela mensal pelo sistema PRICE (anuidade)."""
    if months == 0:
        return 0.0
    if monthly_rate == 0:
        return principal / months
    r = monthly_rate
    payment = r * principal / (1 - (1 + r) ** (-months))
    return payment

def financing_amortization_schedule(
    property_value: float,
    down_payment: float,
    months: int,
    annual_interest_pct: float,
    insurance_annual_pct: float = 0.0,
    other_upfront_fees_pct: float = 0.0,
    other_monthly_fees_pct_on_balance: float = 0.0,
):
    """
    Gera tabela detalhada de amortização mensal (PRICE) com componentes:
    - saldo inicial, juros, amortização (principal), seguro, outras taxas mensais, parcela total, saldo final.
    Retorna DataFrame com meses 0..N (0 = desembolso: entrada + taxas upfront).
    """
    financed_amount = property_value - down_payment
    monthly_interest = annual_interest_pct / 100.0 / 12.0
    payment = annuity_payment(financed_amount, monthly_interest, months)

    upfront_fee = other_upfront_fees_pct / 100.0 * financed_amount

    # construir linhas
    rows = []
    # t=0 desembolso (entrada + upfront fee) - representado como pagamento (positivo = saída)
    rows.append({
        "month": 0,
        "saldo_inicial": financed_amount,
        "juros": 0.0,
        "amortizacao": 0.0,
        "seguro": 0.0,
        "outras_taxas": upfront_fee,
        "parcela": down_payment + upfront_fee,
        "saldo_final": financed_amount
    })

    balance = financed_amount
    for m in range(1, months + 1):
        interest_comp = monthly_interest * balance
        amort = payment - interest_comp
        # atualiza saldo
        saldo_final = max(balance - amort, 0.0)
        # seguro como % anual sobre saldo inicial financiado (aprox. simplificação)
        seguro_mensal = insurance_annual_pct / 100.0 / 12.0 * financed_amount
        outras_taxas_mensais = other_monthly_fees_pct_on_balance / 100.0 / 12.0 * balance
        parcela_total = payment + seguro_mensal + outras_taxas_mensais

        rows.append({
            "month": m,
            "saldo_inicial": balance,
            "juros": interest_comp,
            "amortizacao": amort,
            "seguro": seguro_mensal,
            "outras_taxas": outras_taxas_mensais,
            "parcela": parcela_total,
            "saldo_final": saldo_final
        })

        balance = saldo_final

    df = pd.DataFrame(rows)
    return df

def compute_consorcio_cashflows(
    credit_value: float,
    months: int,
    admin_annual_pct: float = 0.0,
    reserve_monthly_pct: float = 0.0,
    initial_bid_payment: float = 0.0
):
    """
    Fluxo simplificado do consórcio:
    - t=0: lance/entrada (opcional)
    - meses 1..N: amortização linear (crédito / months) + admin_monthly + reserve_monthly
    Retorna DataFrame meses 0..N com colunas componentes.
    """
    parcel_base = credit_value / months if months > 0 else 0.0
    admin_monthly = admin_annual_pct / 100.0 / 12.0 * credit_value
    reserve_monthly = reserve_monthly_pct / 100.0 * credit_value

    rows = []
    rows.append({
        "month": 0,
        "amortizacao": 0.0,
        "admin": 0.0,
        "reserva": initial_bid_payment,
        "parcela": initial_bid_payment
    })
    for m in range(1, months + 1):
        parcela_total = parcel_base + admin_monthly + reserve_monthly
        rows.append({
            "month": m,
            "amortizacao": parcel_base,
            "admin": admin_monthly,
            "reserva": reserve_monthly,
            "parcela": parcela_total
        })
    df = pd.DataFrame(rows)
    return df

def monthly_irr_from_cashflows(cashflows: pd.Series):
    try:
        rate = np.irr(cashflows.values)
        return rate
    except Exception:
        return np.nan

def to_annual_from_monthly(monthly_rate):
    if monthly_rate is None or np.isnan(monthly_rate):
        return np.nan
    return (1 + monthly_rate) ** 12 - 1

def compute_vpl(cashflows: pd.Series, annual_discount_pct: float):
    monthly_discount = (1 + annual_discount_pct / 100.0) ** (1/12) - 1
    vpl = sum(cf / ((1 + monthly_discount) ** i) for i, cf in enumerate(cashflows))
    return vpl

def required_capital_to_cover_payment(monthly_payment: float, monthly_return_pct: float):
    if monthly_return_pct <= 0:
        return np.nan
    return monthly_payment / monthly_return_pct

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Comparador: Financiamento x Consórcio", layout="wide")
st.title("🔎 Comparador: Financiamento Imobiliário × Consórcio — CET, VPL, Amortização e Gráficos")

st.markdown("Preencha os dois cenários, clique em **Recalcular**. Todos os valores financeiros são exibidos no formato BR (R$ 1.234.567,89).")

with st.form(key="inputs_form"):
    st.subheader("1) Cenário A — Financiamento (ex.: financiamento imobiliário)")
    c1, c2, c3 = st.columns(3)
    with c1:
        fin_property_value = st.number_input("Valor do imóvel (R$)", value=600_000.0, step=1000.0, format="%.2f")
        fin_down_payment = st.number_input("Entrada (R$)", value=120_000.0, step=1000.0, format="%.2f")
    with c2:
        fin_months = st.number_input("Prazo (meses)", min_value=6, max_value=480, value=360, step=1)
        fin_annual_rate = st.number_input("Juro anual (%)", value=9.0, step=0.01)
    with c3:
        fin_insurance_pct = st.number_input("Seguro / taxas anuais (%)", value=0.6, step=0.01)
        fin_upfront_pct = st.number_input("Taxas upfront (% sobre financiado)", value=1.0, step=0.01)
        fin_monthly_fee_pct = st.number_input("Outras taxas anuais sobre saldo (%)", value=0.0, step=0.01)

    st.markdown("---")
    st.subheader("2) Cenário B — Consórcio")
    d1, d2, d3 = st.columns(3)
    with d1:
        cons_credit_value = st.number_input("Crédito / Valor do imóvel (R$)", value=600_000.0, step=1000.0, format="%.2f")
        cons_months = st.number_input("Prazo (meses)", min_value=6, max_value=360, value=180, step=1)
    with d2:
        cons_admin_annual_pct = st.number_input("Taxa de administração anual (%)", value=1.8, step=0.01)
        cons_reserve_monthly_pct = st.number_input("Fundo de reserva mensal (% sobre crédito)", value=0.05, step=0.01)
    with d3:
        cons_initial_bid = st.number_input("Valor de lance/entrada inicial (R$) (opcional)", value=0.0, step=100.0, format="%.2f")

    st.markdown("---")
    st.subheader("3) Simulação de rendimento e VPL")
    e1, e2 = st.columns(2)
    with e1:
        monthly_return_pct_input = st.number_input("Rendimento mensal esperado (%)", value=0.5, step=0.01)
    with e2:
        annual_discount_rate = st.number_input("Taxa de desconto anual para VPL (%)", value=10.0, step=0.1)
    show_monthly_chart = st.checkbox("Mostrar gráfico de comparação mensal (linhas)", value=True)

    recalc = st.form_submit_button("🔁 Recalcular")

if not recalc:
    st.info("Preencha os dados e clique em **Recalcular** para gerar os cálculos e gráficos.")
    st.stop()

# -----------------------------
# Cálculos
# -----------------------------
# Amortização financiamento (detalhada)
df_amort = financing_amortization_schedule(
    property_value=fin_property_value,
    down_payment=fin_down_payment,
    months=int(fin_months),
    annual_interest_pct=float(fin_annual_rate),
    insurance_annual_pct=float(fin_insurance_pct),
    other_upfront_fees_pct=float(fin_upfront_pct),
    other_monthly_fees_pct_on_balance=float(fin_monthly_fee_pct)
)

# Fluxos financeiros do financiamento (serie de cashflows: t=0..N onde negativo = saída)
# Para IRR/VPL, modelamos chegadas do ponto de vista do cliente (saídas positivas => representadas como negativos)
flows_fin = [-row for row in df_amort["parcela"].values]  # parcelas (t=0..N) como saídas -> negativos para TIR
# Note: t=0 included as parcela with entry+upfront

# Consórcio
df_cons = compute_consorcio_cashflows(
    credit_value=cons_credit_value,
    months=int(cons_months),
    admin_annual_pct=float(cons_admin_annual_pct),
    reserve_monthly_pct=float(cons_reserve_monthly_pct),
    initial_bid_payment=float(cons_initial_bid)
)
flows_cons = [-row for row in df_cons["parcela"].values]

# CET via IRR
irr_fin_monthly = monthly_irr_from_cashflows(pd.Series(flows_fin))
irr_cons_monthly = monthly_irr_from_cashflows(pd.Series(flows_cons))
cet_fin_annual = to_annual_from_monthly(irr_fin_monthly)
cet_cons_annual = to_annual_from_monthly(irr_cons_monthly)

# parcelas médias (sem considerar t=0 entrada)
avg_parcel_fin = df_amort.loc[df_amort["month"] != 0, "parcela"].mean()
avg_parcel_cons = df_cons.loc[df_cons["month"] != 0, "parcela"].mean()

# VPL com taxa de desconto informada (entrada em percentual anual)
vpl_fin = compute_vpl(pd.Series(flows_fin), annual_discount_rate)
vpl_cons = compute_vpl(pd.Series(flows_cons), annual_discount_rate)

# capital necessário para cobrir parcela pela taxa de rendimento mensal indicada
monthly_return_frac = monthly_return_pct_input / 100.0
required_capital_fin = required_capital_to_cover_payment(avg_parcel_fin, monthly_return_frac)
required_capital_cons = required_capital_to_cover_payment(avg_parcel_cons, monthly_return_frac)

# -----------------------------
# Exibição resultados - formatação BR aplicada
# -----------------------------
st.header("Resultados — Resumo rápido")

c1, c2 = st.columns(2)
with c1:
    st.subheader("🔹 Financiamento")
    st.markdown(f"- **Parcela média (mês):** {br_currency(avg_parcel_fin)}")
    st.markdown(f"- **CET (aprox. efetivo a.a.):** {br_percent(cet_fin_annual*100) if not np.isnan(cet_fin_annual) else '—'}")
    st.markdown(f"- **VPL (desconto {annual_discount_rate:.2f}% a.a.):** {br_currency(vpl_fin)}")
    upfront_total = fin_down_payment + (fin_upfront_pct/100*(fin_property_value - fin_down_payment))
    st.markdown(f"- **Entrada + taxas upfront:** {br_currency(upfront_total)}")
with c2:
    st.subheader("🔸 Consórcio")
    st.markdown(f"- **Parcela média (mês):** {br_currency(avg_parcel_cons)}")
    st.markdown(f"- **CET (aprox. efetivo a.a.):** {br_percent(cet_cons_annual*100) if not np.isnan(cet_cons_annual) else '—'}")
    st.markdown(f"- **VPL (desconto {annual_discount_rate:.2f}% a.a.):** {br_currency(vpl_cons)}")
    st.markdown(f"- **Lance/entrada inicial:** {br_currency(cons_initial_bid)}")

st.markdown("---")
st.subheader("Simulação: capital necessário para que o rendimento cubra a parcela")
col_fin, col_cons = st.columns(2)
with col_fin:
    st.markdown(f"Rendimento mensal considerado: **{br_percent(monthly_return_pct_input,2)}**")
    if np.isnan(required_capital_fin):
        st.warning("Rendimento 0% ou inválido => capital infinito.")
    else:
        st.markdown(f"**Financiamento:** capital necessário ≈ **{br_currency(required_capital_fin)}**")
with col_cons:
    if np.isnan(required_capital_cons):
        st.warning("Rendimento 0% ou inválido => capital infinito.")
    else:
        st.markdown(f"**Consórcio:** capital necessário ≈ **{br_currency(required_capital_cons)}**")

st.markdown("---")

# -----------------------------
# Amortization table display & download
# -----------------------------
st.subheader("Tabela de Amortização (Financiamento)")
# mostra primeira e últimas linhas, com formato
def df_amort_formatted(df):
    df2 = df.copy()
    df2["saldo_inicial"] = df2["saldo_inicial"].apply(br_currency)
    df2["juros"] = df2["juros"].apply(br_currency)
    df2["amortizacao"] = df2["amortizacao"].apply(br_currency)
    df2["seguro"] = df2["seguro"].apply(br_currency)
    df2["outras_taxas"] = df2["outras_taxas"].apply(br_currency)
    df2["parcela"] = df2["parcela"].apply(br_currency)
    df2["saldo_final"] = df2["saldo_final"].apply(br_currency)
    return df2

st.dataframe(df_amort_formatted(df_amort.head(10)), height=300)
st.markdown("...")
st.dataframe(df_amort_formatted(df_amort.tail(6)), height=200)

csv_amort = df_amort.to_csv(index=False).encode("utf-8")
st.download_button("📥 Baixar tabela de amortização (Financiamento) - CSV", csv_amort, file_name="amortizacao_financiamento.csv", mime="text/csv")

# -----------------------------
# Amostras de fluxos e downloads
# -----------------------------
st.subheader("Amostra dos fluxos (primeiros 6 meses)")
df_fin_flow_sample = pd.DataFrame({
    "month": df_amort["month"],
    "parcela": df_amort["parcela"]
}).head(6).copy()
df_fin_flow_sample["parcela"] = df_fin_flow_sample["parcela"].apply(br_currency)

df_cons_flow_sample = df_cons.head(6).copy()
df_cons_flow_sample["parcela"] = df_cons_flow_sample["parcela"].apply(br_currency)

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Financiamento — primeiros 6 meses**")
    st.table(df_fin_flow_sample.rename(columns={"month":"Mês","parcela":"Parcela (R$)"}))
with c2:
    st.markdown("**Consórcio — primeiros 6 meses**")
    st.table(df_cons_flow_sample.rename(columns={"month":"Mês","parcela":"Parcela (R$)"}))

csv_fin = pd.DataFrame({"month": df_amort["month"], "parcela": df_amort["parcela"]}).to_csv(index=False).encode("utf-8")
csv_cons = df_cons.to_csv(index=False).encode("utf-8")
st.download_button("📥 Baixar fluxo completo - Financiamento (CSV)", csv_fin, file_name="fluxo_financiamento.csv", mime="text/csv")
st.download_button("📥 Baixar fluxo completo - Consórcio (CSV)", csv_cons, file_name="fluxo_consorcio.csv", mime="text/csv")

st.markdown("---")

# -----------------------------
# Gráficos adicionais
# -----------------------------
st.subheader("Gráficos — comparação visual dos fluxos e componentes")

# preparar df para gráficos
max_months = max(int(fin_months), int(cons_months))
months = list(range(0, max_months + 1))
plot_df = pd.DataFrame({"month": months})

# financiar: merge parcelas (preencher 0 onde não existe)
df_fin_plot = pd.DataFrame({"month": df_amort["month"], "parcela_fin": df_amort["parcela"]})
plot_df = plot_df.merge(df_fin_plot, on="month", how="left")
plot_df["parcela_fin"].fillna(0.0, inplace=True)

# consorcio
df_cons_plot = pd.DataFrame({"month": df_cons["month"], "parcela_cons": df_cons["parcela"]})
plot_df = plot_df.merge(df_cons_plot, on="month", how="left")
plot_df["parcela_cons"].fillna(0.0, inplace=True)

# transformar para long form para linhas
df_long = plot_df.melt(id_vars="month", value_vars=["parcela_fin","parcela_cons"],
                       var_name="scenario", value_name="parcela")
df_long["scenario"] = df_long["scenario"].map({"parcela_fin":"Financiamento", "parcela_cons":"Consórcio"})

if show_monthly_chart:
    line = alt.Chart(df_long[df_long["month"]>0]).mark_line(point=True).encode(
        x=alt.X("month:Q", title="Mês"),
        y=alt.Y("parcela:Q", title="Pagamento mensal (R$)"),
        color="scenario:N",
        tooltip=["month","scenario","parcela"]
    ).properties(width=900, height=320)
    st.altair_chart(line, use_container_width=True)
else:
    st.info("Ative o gráfico mensal para visualização.")

# Gráfico 2: pagamentos cumulados
plot_df["cum_fin"] = plot_df["parcela_fin"].cumsum()
plot_df["cum_cons"] = plot_df["parcela_cons"].cumsum()
cum_long = plot_df.melt(id_vars="month", value_vars=["cum_fin","cum_cons"], var_name="scenario", value_name="cum_payment")
cum_long["scenario"] = cum_long["scenario"].map({"cum_fin":"Financiamento","cum_cons":"Consórcio"})

area = alt.Chart(cum_long[cum_long["month"]>0]).mark_area(opacity=0.3).encode(
    x="month:Q",
    y=alt.Y("cum_payment:Q", title="Pagamento acumulado (R$)"),
    color="scenario:N",
    tooltip=["month","scenario","cum_payment"]
).properties(width=900, height=300)
st.altair_chart(area, use_container_width=True)

# Gráfico 3: componentes do financiamento (juros x amortização x seguro x outras)
comp_df = df_amort.copy()
comp_df = comp_df.loc[comp_df["month"]>0, ["month","juros","amortizacao","seguro","outras_taxas"]]
# melt para stacked area
comp_long = comp_df.melt(id_vars="month", var_name="component", value_name="value")
stack = alt.Chart(comp_long).mark_area(opacity=0.6).encode(
    x="month:Q",
    y=alt.Y("value:Q", title="Valor (R$)"),
    color="component:N",
    tooltip=["month","component","value"]
).properties(width=900, height=320)
st.markdown("Componentes do pagamento (Financiamento): juros, amortização (principal), seguro e outras taxas.")
st.altair_chart(stack, use_container_width=True)

# Gráfico 4: CET vs VPL (resumo comparativo)
summary_df = pd.DataFrame({
    "scenario": ["Financiamento","Consórcio"],
    "CET_pct": [cet_fin_annual*100 if not np.isnan(cet_fin_annual) else 0.0,
                cet_cons_annual*100 if not np.isnan(cet_cons_annual) else 0.0],
    "VPL_R$": [vpl_fin, vpl_cons]
})
bar_cet = alt.Chart(summary_df).transform_fold(
    ["CET_pct", "VPL_R$"],
    as_=['metric', 'value']
).mark_bar().encode(
    x=alt.X('scenario:N', title='Cenário'),
    y=alt.Y('value:Q', title='Valor'),
    color='metric:N',
    tooltip=[
        alt.Tooltip('scenario:N', title='Cenário'),
        alt.Tooltip('metric:N', title='Métrica'),
        alt.Tooltip('value:Q', title='Valor', format=',.2f')
    ]
).properties(width=700, height=300)

st.markdown("Comparativo rápido: CET (%) e VPL (R$). (Valores exibidos no tooltip; gráficos são para referência visual.)")
st.altair_chart(bar_cet, use_container_width=True)

st.markdown("---")

# -----------------------------
# Observações / opções de adaptação (texto solicitado)
# -----------------------------
st.subheader("Opções de adaptação (posso customizar para você)")
st.markdown(
    """
    Se quiser, eu adapto:
    **(a)** modelo de amortização detalhado com tabela juros/amortização mês a mês;  
    **(b)** inclusão de imposto e seguro variando por saldo;  
    **(c)** método IFR ou CET oficial conforme regulamento do banco.  
    """
)

st.markdown("Se quiser que eu já gere uma versão com (a), (b) ou (c) ativados por padrão, me diga qual opção que eu adapto o código e entrego o arquivo pronto.")

st.caption("Observação: cálculos e CET são aproximações pedagógicas. Para CET oficial consulte o demonstrativo do agente financeiro/administradora.")
