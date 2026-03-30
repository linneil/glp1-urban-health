"""Streamlit dashboard — GLP-1 × Urban Health."""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

import os as _os
DB_PATH = Path(_os.environ["DASHBOARD_DB_PATH"]) if "DASHBOARD_DB_PATH" in _os.environ else Path(__file__).resolve().parents[1] / "data" / "glp1_health.duckdb"

st.set_page_config(page_title="GLP-1 × Urban Health", layout="wide")
st.title("GLP-1 Drug Approvals × US Obesity Trends")
st.caption("Data sources: OpenFDA · ClinicalTrials.gov · CDC BRFSS · US Census ACS")


# -- helpers --------------------------------------------------------

@st.cache_resource
def get_connection():
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data(ttl=3600)
def query(sql: str) -> pd.DataFrame:
    con = get_connection()
    return con.execute(sql).fetchdf()


# -- Tab definitions ------------------------------------------------

tab1, tab2, tab3, tab4 = st.tabs([
    "GLP-1 Approval Timeline",
    "State Obesity Map",
    "Correlation Analysis",
    "Clinical Trial Map",
])


# ===================================================================
# TAB 1 — GLP-1 Approval Timeline
# ===================================================================
with tab1:
    st.header("GLP-1 Drug Approval Timeline vs. National Obesity Rate")

    milestones = query("SELECT * FROM mart_glp1_timeline ORDER BY approval_date")
    obesity_national = query("""
        SELECT year, AVG(obesity_pct) AS avg_obesity
        FROM mart_state_obesity
        WHERE obesity_pct IS NOT NULL
        GROUP BY year ORDER BY year
    """)

    fig = go.Figure()

    # National obesity trend line
    fig.add_trace(go.Scatter(
        x=obesity_national["year"],
        y=obesity_national["avg_obesity"],
        mode="lines+markers",
        name="National avg obesity %",
        line=dict(color="#2563eb", width=3),
        yaxis="y",
    ))

    # Drug approval markers
    colours = {
        "Obesity": "#dc2626",
        "T2D": "#16a34a",
        "T2D (oral)": "#65a30d",
    }
    for _, row in milestones.iterrows():
        colour = colours.get(row["indication"], "#6b7280")
        fig.add_vline(
            x=row["approval_year"],
            line_dash="dot",
            line_color=colour,
            opacity=0.5,
        )
        fig.add_annotation(
            x=row["approval_year"],
            y=obesity_national["avg_obesity"].max() + 0.8,
            text=f"{row['brand_name']}<br><sub>{row['indication']}</sub>",
            showarrow=False,
            font=dict(size=10, color=colour),
            yshift=10,
        )

    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Adult obesity prevalence (%)",
        height=500,
        margin=dict(t=80),
        legend=dict(yanchor="bottom", y=0.02, xanchor="left", x=0.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Approval details"):
        st.dataframe(milestones, use_container_width=True)


# ===================================================================
# TAB 2 — Choropleth Map
# ===================================================================
with tab2:
    st.header("State-Level Obesity Prevalence")

    obesity = query("SELECT * FROM mart_state_obesity WHERE obesity_pct IS NOT NULL")
    years = sorted(obesity["year"].dropna().unique())

    selected_year = st.select_slider("Year", options=years, value=years[-1])
    df_year = obesity[obesity["year"] == selected_year]

    fig_map = px.choropleth(
        df_year,
        locations="state_abbr",
        locationmode="USA-states",
        color="obesity_pct",
        color_continuous_scale="YlOrRd",
        range_color=(20, 45),
        scope="usa",
        hover_name="state_name",
        hover_data={"obesity_pct": ":.1f", "state_abbr": False},
        labels={"obesity_pct": "Obesity %"},
    )
    fig_map.update_layout(height=500, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_map, use_container_width=True)

    # Trend sparkline for selected states
    st.subheader("Compare state trends")
    all_states = sorted(obesity["state_name"].dropna().unique())
    chosen = st.multiselect("Select states", all_states, default=all_states[:5])
    if chosen:
        df_trend = obesity[obesity["state_name"].isin(chosen)]
        fig_trend = px.line(
            df_trend, x="year", y="obesity_pct", color="state_name",
            labels={"obesity_pct": "Obesity %", "year": "Year", "state_name": "State"},
        )
        fig_trend.update_layout(height=400)
        st.plotly_chart(fig_trend, use_container_width=True)


# ===================================================================
# TAB 3 — Correlation Analysis
# ===================================================================
with tab3:
    st.header("Trial Density vs. Obesity Slope Change")
    st.caption(
        "Comparing each state's obesity rate trend (slope) before and after "
        "Wegovy approval (June 2021). Slope change = post-slope − pre-slope."
    )

    corr = query("SELECT * FROM mart_correlation")

    col1, col2 = st.columns(2)

    with col1:
        fig_scatter = px.scatter(
            corr,
            x="trial_count",
            y="slope_change",
            hover_name="state_name",
            size="post_avg_obesity",
            color="avg_median_income",
            color_continuous_scale="Viridis",
            labels={
                "trial_count": "GLP-1 clinical trials",
                "slope_change": "Obesity slope change (post − pre)",
                "avg_median_income": "Median income",
                "post_avg_obesity": "Avg obesity % (post)",
            },
            trendline="ols",
        )
        fig_scatter.update_layout(height=500)
        st.plotly_chart(fig_scatter, use_container_width=True)

    with col2:
        # Correlation stats
        valid = corr[["trial_count", "slope_change"]].dropna()
        if len(valid) >= 5:
            pr, pp = stats.pearsonr(valid["trial_count"], valid["slope_change"])
            sr, sp = stats.spearmanr(valid["trial_count"], valid["slope_change"])
            st.metric("Pearson r", f"{pr:+.3f}", f"p = {pp:.4f}")
            st.metric("Spearman ρ", f"{sr:+.3f}", f"p = {sp:.4f}")
            st.metric("States (n)", len(valid))
        else:
            st.warning("Not enough data to compute correlations.")

        st.markdown("---")
        st.markdown(
            "**Interpretation note:** This is an ecological correlation study. "
            "A relationship at state level does *not* imply individual-level "
            "causation. Confounders include income, insurance access, state "
            "health policies, and demographic composition."
        )

    with st.expander("Full data table"):
        st.dataframe(
            corr.sort_values("slope_change"),
            use_container_width=True,
        )


# ===================================================================
# TAB 4 — Clinical Trial Site Map
# ===================================================================
with tab4:
    st.header("GLP-1 Clinical Trial Distribution")

    trials = query("""
        SELECT t.*, d.state_abbr
        FROM mart_trial_density t
        LEFT JOIN dim_states d ON t.state = d.state_name
        ORDER BY t.trial_count DESC
    """)

    fig_trials = px.choropleth(
        trials,
        locations="state_abbr",
        locationmode="USA-states",
        color="trial_count",
        color_continuous_scale="Blues",
        scope="usa",
        hover_name="state",
        hover_data={
            "trial_count": True,
            "completed_trials": True,
            "recruiting_trials": True,
            "state_abbr": False,
        },
        labels={"trial_count": "Total trials", "state": "State"},
    )
    fig_trials.update_layout(height=500, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_trials, use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Top 10 states by trial count")
        st.dataframe(trials.head(10), use_container_width=True)
    with col_b:
        fig_bar = px.bar(
            trials.head(15),
            x="trial_count", y="state", orientation="h",
            color="completed_trials",
            labels={"trial_count": "Trials", "state": "State"},
        )
        fig_bar.update_layout(height=450, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_bar, use_container_width=True)
