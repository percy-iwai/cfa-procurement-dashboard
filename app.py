"""
こども家庭庁（CFA）調達DB ダッシュボード
データソース: data/db/cfa_procurement.db
対象期間: FY2023 (R5) 〜 FY2025 (R7、途中)
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="こども家庭庁 調達DB ダッシュボード",
    page_icon="👶",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  #MainMenu {visibility: hidden;}
  footer {visibility: hidden;}
  header {visibility: hidden;}
  div[data-testid="metric-container"] {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 14px 18px;
  }
  div[data-testid="metric-container"] label { font-size: 0.78rem; color: #a6b0cf; }
  .stTabs [data-baseweb="tab"] { font-size: 0.9rem; }
  .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "cfa_procurement.db"
TEMPLATE = "plotly_dark"

# ── 入札方式正規化 ─────────────────────────────────────────────────
def classify_bid(bm: str | None) -> str:
    if not bm:
        return "その他"
    if "随意" in bm:
        return "随意契約"
    if "総合評価" in bm:
        return "一般競争（総合評価）"
    if "一般競争" in bm or "公募型競争" in bm:
        return "一般競争"
    if "企画競争" in bm or "プロポーザル" in bm:
        return "企画競争"
    if "指名競争" in bm:
        return "指名競争"
    return "その他"


BID_COLOR = {
    "一般競争（総合評価）": "#7c83fd",
    "一般競争":             "#74c7ec",
    "随意契約":             "#f38ba8",
    "企画競争":             "#fab387",
    "指名競争":             "#a6e3a1",
    "その他":              "#9399b2",
}


def fmt_oku(v: float) -> str:
    if v >= 10_000:
        return f"{v / 10_000:.2f} 兆円"
    if v >= 1:
        return f"{v:,.1f} 億円"
    return f"{v * 100:.1f} 百万円"


# ── データ読み込み ────────────────────────────────────────────────
@st.cache_data
def load_df() -> pd.DataFrame:
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM contracts", con)
    con.close()

    df["bid_type"] = df["bid_method"].apply(classify_bid)
    df["amount_oku"] = df["contract_amount"].fillna(0) / 1e8
    df["fiscal_year"] = df["fiscal_year"].astype("Int64")
    df["contract_date_dt"] = pd.to_datetime(
        df["contract_date"], format="%Y%m%d", errors="coerce"
    )
    df["year_month"] = df["contract_date_dt"].dt.to_period("M").astype(str).replace("NaT", pd.NA)

    # 担当部局をcontract_deptから抽出
    def extract_dept(s):
        if not s:
            return "不明"
        s = str(s)
        for kw in ["成育局", "支援局", "長官官房", "審議官", "参事官"]:
            if kw in s:
                return kw
        return "その他"
    df["dept"] = df["contracting_dept"].apply(extract_dept)

    return df


# ── ドリルダウン ──────────────────────────────────────────────────
_COLS = {
    "fiscal_year": "FY",
    "bid_type": "入札方式",
    "account_type": "会計区分",
    "procurement_type": "調達種別",
    "dept": "担当部局",
    "contract_name": "件名",
    "vendor_name": "ベンダー",
    "contract_amount": "金額（円）",
    "contract_date": "締結日",
}

try:
    _v = tuple(int(x) for x in st.__version__.split(".")[:2])
    _HAS_DIALOG = _v >= (1, 35)
except Exception:
    _HAS_DIALOG = False

if _HAS_DIALOG:
    @st.dialog("ドリルダウン", width="large")
    def show_dd(df: pd.DataFrame, title: str, max_rows: int = 300):
        cols = {k: v for k, v in _COLS.items() if k in df.columns}
        disp = df.sort_values("contract_amount", ascending=False, na_position="last")[
            list(cols.keys())
        ].head(max_rows).rename(columns=cols)
        if "金額（円）" in disp.columns:
            disp = disp.copy()
            disp["金額（円）"] = disp["金額（円）"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else ""
            )
        st.subheader(title)
        st.dataframe(disp, use_container_width=True, height=560)
        total = df["contract_amount"].sum(min_count=1)
        st.write(f"**{len(df):,}件** / **{fmt_oku(total / 1e8)}**")
else:
    def show_dd(df: pd.DataFrame, title: str, max_rows: int = 300):
        cols = {k: v for k, v in _COLS.items() if k in df.columns}
        disp = df.sort_values("contract_amount", ascending=False, na_position="last")[
            list(cols.keys())
        ].head(max_rows).rename(columns=cols)
        if "金額（円）" in disp.columns:
            disp = disp.copy()
            disp["金額（円）"] = disp["金額（円）"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else ""
            )
        st.subheader(title)
        st.dataframe(disp, use_container_width=True)


# ── メイン ──────────────────────────────────────────────────────
def main():
    st.markdown("## 👶 こども家庭庁 調達DB ダッシュボード")

    with st.expander("データソース・注記", expanded=False):
        st.markdown("""
**データソース:** [こども家庭庁 契約締結状況](https://www.cfa.go.jp/procurement/proper-public-procurement/)

| FY | ファイル | 件数 |
|----|---------|------|
| FY2023 (R5) | 随意契約・競争入札 × 一般会計・年金特別会計 + 公共工事 | 144件 |
| FY2024 (R6) | 同上 | 205件 |
| FY2025 (R7) | 同上（2025年12月時点、途中） | 208件 |

- 金額NULLは予定価格非公表（単価契約等）の案件
- FY2025は年度途中のため集計対象から外すことも可
- CFA設立: 2023年4月1日（令和5年）
        """)

    df = load_df()

    # ── サイドバー：フィルタ ──────────────────────────────────────
    with st.sidebar:
        st.markdown("### フィルタ")
        all_fy = sorted(df["fiscal_year"].dropna().unique().tolist())
        sel_fy = st.multiselect("年度", all_fy, default=all_fy, key="fy")

        all_bid = sorted(df["bid_type"].unique().tolist())
        sel_bid = st.multiselect("入札方式", all_bid, default=all_bid, key="bid")

        all_acc = sorted(df["account_type"].unique().tolist())
        sel_acc = st.multiselect("会計区分", all_acc, default=all_acc, key="acc")

        all_proc = sorted(df["procurement_type"].unique().tolist())
        sel_proc = st.multiselect("調達種別", all_proc, default=all_proc, key="proc")

        st.markdown("---")
        st.markdown("**金額下限（万円）**")
        min_amount = st.number_input("", min_value=0, value=0, step=100, label_visibility="collapsed")

    filt = df[
        df["fiscal_year"].isin(sel_fy)
        & df["bid_type"].isin(sel_bid)
        & df["account_type"].isin(sel_acc)
        & df["procurement_type"].isin(sel_proc)
        & (df["contract_amount"].isna() | (df["contract_amount"] >= min_amount * 10_000))
    ]

    total_amount = filt["contract_amount"].sum(min_count=1) or 0
    total_count = len(filt)
    zuii_count = (filt["bid_type"] == "随意契約").sum()
    zuii_rate = zuii_count / total_count * 100 if total_count > 0 else 0
    zuii_amount = filt[filt["bid_type"] == "随意契約"]["contract_amount"].sum(min_count=1) or 0
    zuii_amount_rate = zuii_amount / total_amount * 100 if total_amount > 0 else 0

    # ── KPIカード ────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("総契約金額", fmt_oku(total_amount / 1e8))
    c2.metric("総件数", f"{total_count:,} 件")
    c3.metric("随意契約率（件数）", f"{zuii_rate:.1f}%")
    c4.metric("随意契約率（金額）", f"{zuii_amount_rate:.1f}%")

    st.markdown("---")

    # ── タブ ─────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 年度トレンド", "🏢 担当部局", "🏭 ベンダー", "📋 入札方式", "🔍 契約一覧"
    ])

    # ── Tab1: 年度トレンド ────────────────────────────────────────
    with tab1:
        by_fy = (
            filt.groupby(["fiscal_year", "bid_type"])["contract_amount"]
            .sum()
            .reset_index()
        )
        by_fy["amount_oku"] = by_fy["contract_amount"] / 1e8
        fig1 = px.bar(
            by_fy,
            x="fiscal_year",
            y="amount_oku",
            color="bid_type",
            color_discrete_map=BID_COLOR,
            barmode="stack",
            labels={"fiscal_year": "年度", "amount_oku": "金額（億円）", "bid_type": "入札方式"},
            template=TEMPLATE,
            title="年度別・入札方式別 契約金額",
        )
        fig1.update_layout(height=400, xaxis=dict(tickmode="linear", dtick=1))
        st.plotly_chart(fig1, use_container_width=True)

        col1, col2 = st.columns(2)

        with col1:
            by_fy_cnt = (
                filt.groupby(["fiscal_year", "bid_type"])
                .size()
                .reset_index(name="count")
            )
            fig_cnt = px.bar(
                by_fy_cnt,
                x="fiscal_year",
                y="count",
                color="bid_type",
                color_discrete_map=BID_COLOR,
                barmode="stack",
                labels={"fiscal_year": "年度", "count": "件数", "bid_type": "入札方式"},
                template=TEMPLATE,
                title="年度別・入札方式別 件数",
            )
            fig_cnt.update_layout(height=350, xaxis=dict(tickmode="linear", dtick=1))
            st.plotly_chart(fig_cnt, use_container_width=True)

        with col2:
            by_acc = (
                filt.groupby(["fiscal_year", "account_type"])["contract_amount"]
                .sum()
                .reset_index()
            )
            by_acc["amount_oku"] = by_acc["contract_amount"] / 1e8
            fig_acc = px.bar(
                by_acc,
                x="fiscal_year",
                y="amount_oku",
                color="account_type",
                barmode="stack",
                labels={"fiscal_year": "年度", "amount_oku": "金額（億円）", "account_type": "会計"},
                template=TEMPLATE,
                title="年度別・会計区分別 金額",
            )
            fig_acc.update_layout(height=350, xaxis=dict(tickmode="linear", dtick=1))
            st.plotly_chart(fig_acc, use_container_width=True)

        # 月次トレンド
        monthly = (
            filt.dropna(subset=["year_month"])
            .groupby("year_month")["contract_amount"]
            .sum()
            .reset_index()
        )
        monthly = monthly.sort_values("year_month")
        monthly["amount_oku"] = monthly["contract_amount"] / 1e8
        if not monthly.empty:
            fig_m = px.line(
                monthly,
                x="year_month",
                y="amount_oku",
                markers=True,
                labels={"year_month": "年月", "amount_oku": "金額（億円）"},
                template=TEMPLATE,
                title="月次 契約金額推移",
            )
            fig_m.update_layout(height=320)
            st.plotly_chart(fig_m, use_container_width=True)

    # ── Tab2: 担当部局 ────────────────────────────────────────────
    with tab2:
        by_dept = (
            filt.groupby("dept")
            .agg(金額=("contract_amount", "sum"), 件数=("id", "count"))
            .reset_index()
            .sort_values("金額", ascending=False)
        )
        by_dept["金額_oku"] = by_dept["金額"] / 1e8

        fig_dept = px.bar(
            by_dept,
            x="金額_oku",
            y="dept",
            orientation="h",
            color="件数",
            color_continuous_scale="Tealrose",
            labels={"金額_oku": "金額（億円）", "dept": "担当部局"},
            template=TEMPLATE,
            title="担当部局別 契約金額（降順）",
        )
        fig_dept.update_layout(height=400, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_dept, use_container_width=True)

        # 担当部局テーブル
        st.dataframe(
            by_dept.rename(columns={"dept": "担当部局", "金額_oku": "金額（億円）"})
            .assign(**{"金額（億円）": lambda d: d["金額（億円）"].map("{:,.1f}".format)})
            [["担当部局", "件数", "金額（億円）"]],
            use_container_width=True, hide_index=True
        )

    # ── Tab3: ベンダー ────────────────────────────────────────────
    with tab3:
        top_n = st.slider("表示件数", 10, 50, 20, key="topn")
        top_vendors = (
            filt.groupby("vendor_name")
            .agg(金額=("contract_amount", "sum"), 件数=("id", "count"))
            .reset_index()
            .sort_values("金額", ascending=False)
            .head(top_n)
        )
        top_vendors["金額_oku"] = top_vendors["金額"] / 1e8

        fig_v = px.bar(
            top_vendors,
            x="金額_oku",
            y="vendor_name",
            orientation="h",
            color="件数",
            color_continuous_scale="Viridis",
            labels={"金額_oku": "金額（億円）", "vendor_name": "ベンダー"},
            template=TEMPLATE,
            title=f"ベンダー別 契約金額 TOP {top_n}",
        )
        fig_v.update_layout(height=max(350, top_n * 22), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_v, use_container_width=True)

        if st.button("ベンダー一覧をドリルダウン表示"):
            vendor_sel = top_vendors["vendor_name"].tolist()
            show_dd(filt[filt["vendor_name"].isin(vendor_sel)], "ベンダーTOP 契約一覧")

    # ── Tab4: 入札方式 ────────────────────────────────────────────
    with tab4:
        col_l, col_r = st.columns(2)

        with col_l:
            pie_data = (
                filt.groupby("bid_type")["contract_amount"]
                .sum()
                .reset_index()
            )
            pie_data["amount_oku"] = pie_data["contract_amount"] / 1e8
            fig_pie = px.pie(
                pie_data,
                names="bid_type",
                values="amount_oku",
                color="bid_type",
                color_discrete_map=BID_COLOR,
                template=TEMPLATE,
                title="入札方式別 金額構成比",
                hole=0.35,
            )
            fig_pie.update_traces(
                texttemplate="%{label}<br>%{value:.1f}億円",
                textposition="outside"
            )
            fig_pie.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_r:
            pie_cnt = (
                filt.groupby("bid_type")
                .size()
                .reset_index(name="件数")
            )
            fig_pie2 = px.pie(
                pie_cnt,
                names="bid_type",
                values="件数",
                color="bid_type",
                color_discrete_map=BID_COLOR,
                template=TEMPLATE,
                title="入札方式別 件数構成比",
                hole=0.35,
            )
            fig_pie2.update_traces(
                texttemplate="%{label}<br>%{value}件",
                textposition="outside"
            )
            fig_pie2.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig_pie2, use_container_width=True)

        # 随意契約 理由
        if "随意契約" in filt["bid_type"].values:
            zuii_df = filt[filt["bid_type"] == "随意契約"].copy()
            zuii_df["reason_short"] = zuii_df["zuii_reason"].str.extract(
                r"(会計法第\d+条[^\n（]*)", expand=False
            ).fillna("その他")
            by_reason = (
                zuii_df.groupby("reason_short")
                .agg(金額=("contract_amount", "sum"), 件数=("id", "count"))
                .reset_index()
                .sort_values("金額", ascending=False)
            )
            by_reason["金額_oku"] = by_reason["金額"] / 1e8
            fig_r = px.bar(
                by_reason,
                x="金額_oku",
                y="reason_short",
                orientation="h",
                color="件数",
                color_continuous_scale="Reds",
                labels={"金額_oku": "金額（億円）", "reason_short": "随意理由"},
                template=TEMPLATE,
                title="随意契約 根拠条文別 金額",
            )
            fig_r.update_layout(height=350, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_r, use_container_width=True)

    # ── Tab5: 契約一覧 ────────────────────────────────────────────
    with tab5:
        search = st.text_input("件名・ベンダー名で検索", placeholder="キーワード入力...")
        disp_df = filt.copy()
        if search:
            mask = (
                disp_df["contract_name"].fillna("").str.contains(search, case=False)
                | disp_df["vendor_name"].fillna("").str.contains(search, case=False)
            )
            disp_df = disp_df[mask]

        st.write(f"**{len(disp_df):,}件**（フィルタ後）")

        show_cols = {
            "fiscal_year": "FY",
            "contract_date": "締結日",
            "bid_type": "入札方式",
            "account_type": "会計",
            "procurement_type": "種別",
            "contract_name": "件名",
            "vendor_name": "ベンダー",
            "contract_amount": "金額（円）",
            "award_rate": "落札率",
            "notes": "備考",
        }
        show = {k: v for k, v in show_cols.items() if k in disp_df.columns}
        table = (
            disp_df.sort_values("contract_amount", ascending=False, na_position="last")
            [list(show.keys())]
            .rename(columns=show)
        )
        if "金額（円）" in table.columns:
            table = table.copy()
            table["金額（円）"] = table["金額（円）"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else ""
            )
        if "落札率" in table.columns:
            table = table.copy()
            table["落札率"] = table["落札率"].apply(
                lambda x: f"{x:.3f}" if pd.notna(x) else ""
            )
        st.dataframe(table, use_container_width=True, height=560)


if __name__ == "__main__":
    main()
