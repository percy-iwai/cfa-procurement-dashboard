"""
こども家庭庁（CFA）調達DB ダッシュボード
データソース: data/cfa_procurement.db
対象期間: FY2023 (R5) 〜 FY2025 (R7、途中)
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
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
  div[data-testid="stDialog"] > div {
    width: 95vw !important;
    max-width: 95vw !important;
    height: 90vh !important;
    max-height: 90vh !important;
  }
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

# ── 政策分類（予算案4大項目・2階層） ───────────────────────────────
# (大項目, 中項目, キーワードリスト)
_CLASS_RULES: list[tuple[str, str, list[str]]] = [
    # ④ 成育環境にかかわらず誰一人取り残さない ─ 中項目別に優先度高い順
    ("④ 成育環境にかかわらず誰一人取り残さない",
     "こどもの自殺対策",
     ["自殺"]),
    ("④ 成育環境にかかわらず誰一人取り残さない",
     "障害児・医療的ケア児支援等",
     ["障害児", "医療的ケア", "補装具", "発達の特性"]),
    ("④ 成育環境にかかわらず誰一人取り残さない",
     "児童虐待防止・社会的養護・ヤングケアラー支援等",
     ["虐待", "ヤングケアラー", "社会的養護", "里親", "養子縁組", "児童相談",
      "一時保護", "児童養護", "要保護", "アウトリーチ", "訪問支援",
      "国立児童自立", "若者シェルター", "児童福祉司", "死亡検証"]),
    ("④ 成育環境にかかわらず誰一人取り残さない",
     "こどもの貧困対策・ひとり親家庭の自立促進等",
     ["いじめ", "不登校", "ひとり親", "養育費", "貧困", "こども食堂",
      "母子自立", "父子自立", "こどもの未来応援", "寡婦", "フードバンク",
      "こどもの居場所", "宅食", "ひきこもり", "犯罪", "性被害",
      "旧優生保護法", "こども性暴力", "若者総合相談", "若者支援地域"]),

    # ③ 全てのこどもに健やかで安全・安心に成長できる環境の提供
    ("③ 全てのこどもに健やかで安全・安心に成長できる環境の提供",
     "総合的な子育て支援",
     ["企業主導型保育", "保育士", "放課後児童", "病児保育", "子育て支援拠点",
      "保育所", "幼稚園", "認定こども園", "保育業務", "保育実践",
      "こども誰でも通園", "送迎用バス", "健全育成", "幼児期までのこどもの育ち",
      "幼児教育", "地域支援体制整備", "子どもの預かりサービス"]),

    # ② 結婚・妊娠・出産・子育てに夢や希望を感じられる社会の実現
    ("② 結婚・妊娠・出産・子育てに夢や希望を感じられる社会の実現",
     "高等教育の無償化",
     ["修学支援", "高等教育"]),
    ("② 結婚・妊娠・出産・子育てに夢や希望を感じられる社会の実現",
     "妊娠期から子育て期の包括的な切れ目のない支援",
     ["妊娠", "出産", "不妊", "産後", "伴走型", "妊婦", "ドナーミルク",
      "出生前検査", "成育医療", "健やか親子", "乳幼児栄養", "母子保健",
      "プレコンセプション", "生活支援特別給付金", "こどもの福祉と保健"]),
    ("② 結婚・妊娠・出産・子育てに夢や希望を感じられる社会の実現",
     "地域の実情や課題に応じた少子化対策",
     ["少子化", "ライフデザイン", "結婚支援", "少子高齢化セミナー",
      "結婚応援", "母子家庭の母"]),

    # ⑤ 庁内管理・その他
    ("⑤ 庁内管理・その他",
     "庁内管理・その他",
     ["賃貸借", "ビルディング", "警備", "セキュリティ", "電話交換", "乗用自動車",
      "運行管理", "リース車", "健康診断", "新聞", "コピー用紙", "文房具", "防災用品",
      "PMO", "ＰＭＯ", "速記", "官報", "タクシー", "行政文書", "引越", "什器",
      "駐車場", "吸音", "テレキューブ", "叙勲", "出張", "反訳", "国会審議",
      "ライセンス", "タブレット端末", "法令Web", "クリッピング", "切り抜き",
      "ニュースサービス", "庁費", "情報システム", "給与", "清掃", "保守",
      "賃借", "印刷", "メンテナンス", "料金計器", "SPIDER", "D1-Law",
      "判例秘書", "記事利用許諾", "備品", "Wi-Fi", "扉設置", "扉増設",
      "WEB会議", "ヘルプデスク", "業務端末", "Firewall", "会計業務"]),

    # ① こどもの視点に立った司令塔機能の発揮
    ("① こどもの視点に立った司令塔機能の発揮",
     "こども政策DX推進・情報基盤整備",
     ["DX", "ＤＸ", "デジタル", "システム", "データ", "基盤", "ウェブサイト",
      "ホームページ", "EBPM", "インターネット", "WEBサイト", "アクセシビリティ",
      "情報収集", "漫画冊子", "パンフレット", "冊子制作", "動画"]),
    ("① こどもの視点に立った司令塔機能の発揮",
     "こどもまんなか社会の実現・意見反映推進",
     ["意見反映", "意識調査", "こども・若者", "ウェルビーイング", "こども政策",
      "こどもまんなか", "こどもと若者", "自治体こども計画", "こども基本法",
      "こどもの育ちビジョン", "こども未来戦略", "Yahoo", "霞が関見学",
      "普及啓発", "調査研究", "こども未来戦略"]),
    ("① こどもの視点に立った司令塔機能の発揮",
     "広報・情報発信",
     ["広報", "PR"]),
]

CAT_COLOR = {
    "① こどもの視点に立った司令塔機能の発揮":                              "#7c83fd",
    "② 結婚・妊娠・出産・子育てに夢や希望を感じられる社会の実現":           "#f38ba8",
    "③ 全てのこどもに健やかで安全・安心に成長できる環境の提供":             "#a6e3a1",
    "④ 成育環境にかかわらず誰一人取り残さない":                            "#fab387",
    "⑤ 庁内管理・その他":                                                "#9399b2",
}
CAT_ORDER = list(CAT_COLOR.keys())


def classify_contract(name: str | None) -> tuple[str, str]:
    """(大項目, 中項目) を返す。マッチしない場合は ⑤ 庁内管理・その他 にフォールバック。"""
    if not name:
        return ("⑤ 庁内管理・その他", "庁内管理・その他")
    for cat, subcat, keywords in _CLASS_RULES:
        if any(kw in name for kw in keywords):
            return (cat, subcat)
    return ("⑤ 庁内管理・その他", "庁内管理・その他")


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

    def extract_dept(s):
        if not s:
            return "不明"
        s = str(s)
        for kw in ["成育局", "支援局", "長官官房", "審議官", "参事官"]:
            if kw in s:
                return kw
        return "その他"
    df["dept"] = df["contracting_dept"].apply(extract_dept)

    cats = df["contract_name"].apply(classify_contract)
    df["category"]    = cats.apply(lambda t: t[0])
    df["subcategory"] = cats.apply(lambda t: t[1])

    return df


# ── ドリルダウン ──────────────────────────────────────────────────
_DRILLDOWN_COLS = {
    "fiscal_year":     "FY",
    "contract_date":   "締結日",
    "category":        "大項目",
    "subcategory":     "中項目",
    "bid_type":        "入札方式",
    "account_type":    "会計区分",
    "procurement_type":"調達種別",
    "dept":            "担当部局",
    "contract_name":   "件名",
    "vendor_name":     "ベンダー",
    "contract_amount": "金額（円）",
    "award_rate":      "落札率",
    "zuii_reason":     "随意理由",
}

try:
    _v = tuple(int(x) for x in st.__version__.split(".")[:2])
    _HAS_DIALOG = _v >= (1, 35)
except Exception:
    _HAS_DIALOG = False

if _HAS_DIALOG:
    @st.dialog("ドリルダウン", width="large")
    def show_dd(df: pd.DataFrame, title: str, max_rows: int = 300):
        cols = {k: v for k, v in _DRILLDOWN_COLS.items() if k in df.columns}
        disp = (
            df.sort_values("contract_amount", ascending=False, na_position="last")
            [list(cols.keys())]
            .head(max_rows)
            .rename(columns=cols)
        )
        if "金額（円）" in disp.columns:
            disp = disp.copy()
            disp["金額（円）"] = disp["金額（円）"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else ""
            )
        if "落札率" in disp.columns:
            disp = disp.copy()
            disp["落札率"] = disp["落札率"].apply(
                lambda x: f"{x:.3f}" if pd.notna(x) else ""
            )
        st.subheader(title)
        st.dataframe(disp, use_container_width=True, height=600)
        total = df["contract_amount"].sum(min_count=1) or 0
        st.caption(f"{len(df):,} 件 ／ {fmt_oku(total / 1e8)}")
else:
    def show_dd(df: pd.DataFrame, title: str, max_rows: int = 300):
        cols = {k: v for k, v in _DRILLDOWN_COLS.items() if k in df.columns}
        disp = (
            df.sort_values("contract_amount", ascending=False, na_position="last")
            [list(cols.keys())]
            .head(max_rows)
            .rename(columns=cols)
        )
        if "金額（円）" in disp.columns:
            disp = disp.copy()
            disp["金額（円）"] = disp["金額（円）"].apply(
                lambda x: f"{x:,.0f}" if pd.notna(x) else ""
            )
        st.subheader(title)
        st.dataframe(disp, use_container_width=True)
        total = df["contract_amount"].sum(min_count=1) or 0
        st.caption(f"{len(df):,} 件 ／ {fmt_oku(total / 1e8)}")


def _pts(sel) -> list:
    """plotly_chart on_select の結果からポイントリストを安全に取得"""
    if not sel:
        return []
    return sel.get("selection", {}).get("points", [])


# ── メイン ──────────────────────────────────────────────────────
def main():
    st.markdown("## 👶 こども家庭庁 調達DB ダッシュボード")

    with st.expander("データソース・注記", expanded=False):
        st.markdown("""
**データソース:** [こども家庭庁 契約締結状況](https://www.cfa.go.jp/procurement/proper-public-procurement/)

| FY | 件数 |
|----|------|
| FY2023 (R5) | 144件 |
| FY2024 (R6) | 205件 |
| FY2025 (R7) | 208件（2025年12月時点・途中） |

グラフの棒・セグメントをクリックすると該当契約一覧をモーダル表示します。
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

        sel_cat = st.multiselect("政策分類（大項目）", CAT_ORDER, default=CAT_ORDER, key="cat")

        st.markdown("---")
        st.markdown("**金額下限（万円）**")
        min_amount = st.number_input("", min_value=0, value=0, step=100, label_visibility="collapsed")

    filt = df[
        df["fiscal_year"].isin(sel_fy)
        & df["bid_type"].isin(sel_bid)
        & df["account_type"].isin(sel_acc)
        & df["procurement_type"].isin(sel_proc)
        & df["category"].isin(sel_cat)
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
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 年度トレンド", "🏢 担当部局", "🏭 ベンダー", "📋 入札方式",
        "🔍 契約一覧", "💰 予算比較", "📂 政策分類",
    ])

    # ────────────────────────────────────────────────────────────
    # Tab1: 年度トレンド
    # ────────────────────────────────────────────────────────────
    with tab1:
        # ── 年度 × 入札方式 積み上げ棒（クリックでドリルダウン） ──
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
            custom_data=["bid_type"],
            labels={"fiscal_year": "年度", "amount_oku": "金額（億円）", "bid_type": "入札方式"},
            template=TEMPLATE,
            title="年度別・入札方式別 契約金額",
        )
        fig1.update_layout(height=400, xaxis=dict(tickmode="linear", dtick=1))
        sel1 = st.plotly_chart(fig1, use_container_width=True, on_select="rerun", key="fig1")
        st.caption("(クリックでドリルダウン)")
        pts1 = _pts(sel1)
        if pts1:
            pt = pts1[0]
            fy_sel = int(pt["x"])
            bt_sel = pt.get("customdata", [None])[0]
            sub = filt[filt["fiscal_year"] == fy_sel]
            if bt_sel:
                sub = sub[sub["bid_type"] == bt_sel]
                show_dd(sub, f"FY{fy_sel} ／ {bt_sel}")
            else:
                show_dd(sub, f"FY{fy_sel}")

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
                custom_data=["bid_type"],
                labels={"fiscal_year": "年度", "count": "件数", "bid_type": "入札方式"},
                template=TEMPLATE,
                title="年度別・入札方式別 件数",
            )
            fig_cnt.update_layout(height=350, xaxis=dict(tickmode="linear", dtick=1))
            sel_cnt = st.plotly_chart(fig_cnt, use_container_width=True, on_select="rerun", key="fig_cnt")
            pts_cnt = _pts(sel_cnt)
            if pts_cnt:
                pt = pts_cnt[0]
                fy_sel = int(pt["x"])
                bt_sel = pt.get("customdata", [None])[0]
                sub = filt[filt["fiscal_year"] == fy_sel]
                if bt_sel:
                    sub = sub[sub["bid_type"] == bt_sel]
                    show_dd(sub, f"FY{fy_sel} ／ {bt_sel}")
                else:
                    show_dd(sub, f"FY{fy_sel}")

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
                custom_data=["account_type"],
                labels={"fiscal_year": "年度", "amount_oku": "金額（億円）", "account_type": "会計"},
                template=TEMPLATE,
                title="年度別・会計区分別 金額",
            )
            fig_acc.update_layout(height=350, xaxis=dict(tickmode="linear", dtick=1))
            sel_acc2 = st.plotly_chart(fig_acc, use_container_width=True, on_select="rerun", key="fig_acc")
            pts_acc2 = _pts(sel_acc2)
            if pts_acc2:
                pt = pts_acc2[0]
                fy_sel = int(pt["x"])
                acc_sel = pt.get("customdata", [None])[0]
                sub = filt[filt["fiscal_year"] == fy_sel]
                if acc_sel:
                    sub = sub[sub["account_type"] == acc_sel]
                    show_dd(sub, f"FY{fy_sel} ／ {acc_sel}")
                else:
                    show_dd(sub, f"FY{fy_sel}")

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
                custom_data=["year_month"],
                labels={"year_month": "年月", "amount_oku": "金額（億円）"},
                template=TEMPLATE,
                title="月次 契約金額推移",
            )
            fig_m.update_layout(height=320)
            sel_m = st.plotly_chart(fig_m, use_container_width=True, on_select="rerun", key="fig_m")
            pts_m = _pts(sel_m)
            if pts_m:
                pt = pts_m[0]
                ym_sel = pt.get("x") or (pt.get("customdata", [None])[0])
                if ym_sel:
                    sub = filt[filt["year_month"] == str(ym_sel)]
                    show_dd(sub, f"月次: {ym_sel}")

    # ────────────────────────────────────────────────────────────
    # Tab2: 担当部局
    # ────────────────────────────────────────────────────────────
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
            custom_data=["dept"],
            labels={"金額_oku": "金額（億円）", "dept": "担当部局"},
            template=TEMPLATE,
            title="担当部局別 契約金額（降順）",
        )
        fig_dept.update_layout(height=400, yaxis=dict(autorange="reversed"))
        sel_dept = st.plotly_chart(fig_dept, use_container_width=True, on_select="rerun", key="fig_dept")
        st.caption("(クリックでドリルダウン)")
        pts_dept = _pts(sel_dept)
        if pts_dept:
            pt = pts_dept[0]
            dept_name = pt.get("y") or (pt.get("customdata", [None])[0])
            if dept_name:
                sub = filt[filt["dept"] == dept_name]
                show_dd(sub, f"担当部局: {dept_name}")

        st.dataframe(
            by_dept.rename(columns={"dept": "担当部局", "金額_oku": "金額（億円）"})
            .assign(**{"金額（億円）": lambda d: d["金額（億円）"].map("{:,.1f}".format)})
            [["担当部局", "件数", "金額（億円）"]],
            use_container_width=True, hide_index=True,
        )

    # ────────────────────────────────────────────────────────────
    # Tab3: ベンダー
    # ────────────────────────────────────────────────────────────
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
            custom_data=["vendor_name"],
            labels={"金額_oku": "金額（億円）", "vendor_name": "ベンダー"},
            template=TEMPLATE,
            title=f"ベンダー別 契約金額 TOP {top_n}",
        )
        fig_v.update_layout(
            height=max(350, top_n * 22),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11), automargin=True),
            margin=dict(l=250),
        )
        sel_v = st.plotly_chart(fig_v, use_container_width=True, on_select="rerun", key="fig_v")
        st.caption("(クリックでドリルダウン)")
        pts_v = _pts(sel_v)
        if pts_v:
            pt = pts_v[0]
            vname = pt.get("y") or (pt.get("customdata", [None])[0])
            if vname:
                sub = filt[filt["vendor_name"] == vname]
                show_dd(sub, f"ベンダー: {vname}")

    # ────────────────────────────────────────────────────────────
    # Tab4: 入札方式
    # ────────────────────────────────────────────────────────────
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
                textposition="outside",
            )
            fig_pie.update_layout(height=420, showlegend=False)
            sel_pie = st.plotly_chart(fig_pie, use_container_width=True, on_select="rerun", key="fig_pie")
            st.caption("(クリックでドリルダウン)")
            pts_pie = _pts(sel_pie)
            if pts_pie:
                pt = pts_pie[0]
                bt_sel = pt.get("label") or (pt.get("customdata", [None])[0])
                if bt_sel:
                    sub = filt[filt["bid_type"] == bt_sel]
                    show_dd(sub, f"入札方式: {bt_sel}")

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
                textposition="outside",
            )
            fig_pie2.update_layout(height=420, showlegend=False)
            sel_pie2 = st.plotly_chart(fig_pie2, use_container_width=True, on_select="rerun", key="fig_pie2")
            st.caption("(クリックでドリルダウン)")
            pts_pie2 = _pts(sel_pie2)
            if pts_pie2:
                pt = pts_pie2[0]
                bt_sel = pt.get("label") or (pt.get("customdata", [None])[0])
                if bt_sel:
                    sub = filt[filt["bid_type"] == bt_sel]
                    show_dd(sub, f"入札方式: {bt_sel}")

        # 随意契約 理由別棒グラフ
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
                custom_data=["reason_short"],
                labels={"金額_oku": "金額（億円）", "reason_short": "随意理由"},
                template=TEMPLATE,
                title="随意契約 根拠条文別 金額",
            )
            fig_r.update_layout(height=350, yaxis=dict(autorange="reversed"))
            sel_r = st.plotly_chart(fig_r, use_container_width=True, on_select="rerun", key="fig_r")
            st.caption("(クリックでドリルダウン)")
            pts_r = _pts(sel_r)
            if pts_r:
                pt = pts_r[0]
                reason_sel = pt.get("y") or (pt.get("customdata", [None])[0])
                if reason_sel:
                    sub = zuii_df[zuii_df["reason_short"] == reason_sel]
                    show_dd(sub, f"随意理由: {reason_sel}")

    # ────────────────────────────────────────────────────────────
    # Tab5: 契約一覧
    # ────────────────────────────────────────────────────────────
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
            "fiscal_year":     "FY",
            "contract_date":   "締結日",
            "category":        "大項目",
            "subcategory":     "中項目",
            "bid_type":        "入札方式",
            "account_type":    "会計",
            "procurement_type":"種別",
            "contract_name":   "件名",
            "vendor_name":     "ベンダー",
            "contract_amount": "金額（円）",
            "award_rate":      "落札率",
            "notes":           "備考",
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


    # ────────────────────────────────────────────────────────────
    # Tab6: 予算比較
    # ────────────────────────────────────────────────────────────
    with tab6:
        # 予算データ（調査結果に基づく静的値）
        BUDGET_DF = pd.DataFrame([
            {"fiscal_year": 2023, "歳出総額_cho": 4.8, "調達母数_oku": 100.0},
            {"fiscal_year": 2024, "歳出総額_cho": 5.3, "調達母数_oku": 150.0},
            {"fiscal_year": 2025, "歳出総額_cho": 7.3, "調達母数_oku": 200.0},
        ])

        # DB収録額（フィルタ前・全件）
        db_by_fy = (
            df.groupby("fiscal_year")["contract_amount"]
            .sum()
            .reset_index()
            .rename(columns={"contract_amount": "db_total"})
        )
        db_by_fy["DB収録額_oku"] = db_by_fy["db_total"] / 1e8
        db_by_fy["fiscal_year"] = db_by_fy["fiscal_year"].astype(int)

        merged = BUDGET_DF.merge(
            db_by_fy[["fiscal_year", "DB収録額_oku"]], on="fiscal_year", how="left"
        )
        merged["カバレッジ率"] = (
            merged["DB収録額_oku"] / merged["調達母数_oku"] * 100
        ).round(1)

        # ── KPIカード: 歳出総額 ──────────────────────────────────
        st.markdown("### 歳出総額（参考・年度別初期予算）")
        kk1, kk2, kk3 = st.columns(3)
        kk1.metric(
            "FY2023 歳出総額", "約 4.8 兆円",
            help="一般会計初期予算（設立初年度、2023年4月〜）",
        )
        kk2.metric(
            "FY2024 歳出総額", "約 5.3 兆円",
            help="一般会計4.15兆円（各目明細書確認値）＋年金特別会計",
        )
        kk3.metric(
            "FY2025 歳出総額", "約 7.3 兆円",
            help="こども金庫（子ども・子育て支援特別会計）新設により大幅増",
        )

        st.info(
            "💡 歳出の97%以上は**児童手当・保育給付等の移転支出**（地方・独法等へ直接交付）。"
            "「調達母数」は庁費・委託費・情報処理費等、こども家庭庁が直接発注する調達的経費の推計値です。"
        )

        # ── メインチャート: 調達母数 vs DB収録額 ──────────────────
        st.markdown("### 調達母数（推計）vs DB収録額")

        bar_df = pd.melt(
            merged,
            id_vars=["fiscal_year"],
            value_vars=["調達母数_oku", "DB収録額_oku"],
            var_name="区分",
            value_name="金額（億円）",
        )
        bar_df["区分"] = bar_df["区分"].map({
            "調達母数_oku": "調達母数（推計）",
            "DB収録額_oku": "DB収録額",
        })

        fig_bgt = px.bar(
            bar_df,
            x="fiscal_year",
            y="金額（億円）",
            color="区分",
            barmode="group",
            text="金額（億円）",
            color_discrete_map={
                "調達母数（推計）": "#fab387",
                "DB収録額":        "#7c83fd",
            },
            labels={"fiscal_year": "年度", "区分": ""},
            template=TEMPLATE,
            title="調達母数（推計）と DB収録額の比較（億円）",
        )
        fig_bgt.update_traces(texttemplate="%{text:.0f}億", textposition="outside")
        fig_bgt.update_layout(
            height=420,
            xaxis=dict(tickmode="linear", dtick=1),
            yaxis=dict(range=[0, 260]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_bgt, use_container_width=True)

        # ── カバレッジ表 ─────────────────────────────────────────
        st.markdown("### カバレッジ率")
        cov_rows = []
        for _, r in merged.iterrows():
            fy = int(r["fiscal_year"])
            note = "※途中データ（〜2025年12月）" if fy == 2025 else ""
            cov_rows.append({
                "年度": f"FY{fy}",
                "歳出総額（兆円）": f"{r['歳出総額_cho']:.1f}",
                "調達母数推計（億円）": f"{r['調達母数_oku']:.0f}",
                "DB収録額（億円）": f"{r['DB収録額_oku']:.1f}" if pd.notna(r["DB収録額_oku"]) else "—",
                "カバレッジ率": f"{r['カバレッジ率']:.1f}%" if pd.notna(r["カバレッジ率"]) else "—",
                "備考": note,
            })
        st.dataframe(pd.DataFrame(cov_rows), use_container_width=True, hide_index=True)

        # ── 推計根拠 ─────────────────────────────────────────────
        with st.expander("📄 調達母数の推計根拠（FY2024）", expanded=False):
            st.markdown("""
**出典**: 令和6年度内閣府所管 一般会計歳出予算各目明細書（第213回国会提出）

| 項目 | 金額（概算） |
|-----|------------|
| 庁費・情報処理庁費・審議会庁費 | 約 27 億円 |
| こども政策推進事業委託費 | 15.4 億円 |
| 土地建物借料 | 9.7 億円 |
| 各種事業委託費（母子保健・虐待防止・養育費等） | 5.6 億円 |
| 国立施設関連（庁費・食糧費等） | 4.2 億円 |
| **一般会計小計** | **約 62 億円** |
| 年金特別会計分（DB実績から逆算した推計） | 約 88 億円 |
| **合計（調達母数推計）** | **約 150 億円** |

- **FY2023**: 設立初年度（4月以降）のため小規模。DB実績77.7億を基に100億と推計。
- **FY2025**: 7.3兆円規模への拡大（こども金庫設置）を反映し200億と推計。DB収録額は2025年12月時点の途中データ。
- 調達母数には閾値未満の小額契約・非公表契約は含まれていない可能性があります。
""")


    # ────────────────────────────────────────────────────────────
    # Tab7: 政策分類
    # ────────────────────────────────────────────────────────────
    with tab7:
        # ── 大項目別 横棒グラフ ───────────────────────────────────
        by_cat = (
            filt.groupby("category")
            .agg(金額=("contract_amount", "sum"), 件数=("id", "count"))
            .reset_index()
        )
        by_cat["category"] = pd.Categorical(by_cat["category"], categories=CAT_ORDER, ordered=True)
        by_cat = by_cat.sort_values("category")
        by_cat["金額_oku"] = by_cat["金額"] / 1e8

        fig_cat = px.bar(
            by_cat,
            x="金額_oku",
            y="category",
            orientation="h",
            color="category",
            color_discrete_map=CAT_COLOR,
            custom_data=["category"],
            text="金額_oku",
            labels={"金額_oku": "金額（億円）", "category": "大項目"},
            template=TEMPLATE,
            title="予算4大項目別 契約金額",
        )
        fig_cat.update_traces(
            texttemplate="%{text:.1f}億",
            textposition="outside",
            showlegend=False,
        )
        fig_cat.update_layout(
            height=360,
            yaxis=dict(autorange="reversed", tickfont=dict(size=11), automargin=True),
            margin=dict(l=380),
            showlegend=False,
        )
        sel_fig_cat = st.plotly_chart(fig_cat, use_container_width=True, on_select="rerun", key="fig_cat")
        st.caption("(クリックで中項目内訳を表示)")
        pts_cat = _pts(sel_fig_cat)

        if pts_cat:
            pt = pts_cat[0]
            cat_sel = pt.get("y") or (pt.get("customdata", [None])[0])
            if cat_sel:
                sub_df = filt[filt["category"] == cat_sel]

                # 中項目別横棒グラフ（ドリルダウン）
                by_sub = (
                    sub_df.groupby("subcategory")
                    .agg(金額=("contract_amount", "sum"), 件数=("id", "count"))
                    .reset_index()
                    .sort_values("金額", ascending=False)
                )
                by_sub["金額_oku"] = by_sub["金額"] / 1e8
                fig_sub = px.bar(
                    by_sub,
                    x="金額_oku",
                    y="subcategory",
                    orientation="h",
                    color_discrete_sequence=[CAT_COLOR.get(cat_sel, "#7c83fd")],
                    custom_data=["subcategory"],
                    text="金額_oku",
                    labels={"金額_oku": "金額（億円）", "subcategory": "中項目"},
                    template=TEMPLATE,
                    title=f"中項目別 内訳 ── {cat_sel}",
                )
                fig_sub.update_traces(
                    texttemplate="%{text:.1f}億",
                    textposition="outside",
                    showlegend=False,
                )
                fig_sub.update_layout(
                    height=max(280, len(by_sub) * 55),
                    yaxis=dict(autorange="reversed", automargin=True),
                    margin=dict(l=320),
                )
                sel_fig_sub = st.plotly_chart(fig_sub, use_container_width=True, on_select="rerun", key="fig_sub")
                st.caption("(クリックで契約一覧を表示)")
                pts_sub = _pts(sel_fig_sub)
                if pts_sub:
                    pt2 = pts_sub[0]
                    sub_sel = pt2.get("y") or (pt2.get("customdata", [None])[0])
                    if sub_sel:
                        show_dd(sub_df[sub_df["subcategory"] == sub_sel],
                                f"{cat_sel} ／ {sub_sel}")

        st.markdown("---")

        # ── 年度 × 大項目 積み上げ棒グラフ ──────────────────────────
        by_fy_cat = (
            filt.groupby(["fiscal_year", "category"])["contract_amount"]
            .sum()
            .reset_index()
        )
        by_fy_cat["amount_oku"] = by_fy_cat["contract_amount"] / 1e8
        by_fy_cat["category"] = pd.Categorical(
            by_fy_cat["category"], categories=CAT_ORDER, ordered=True
        )
        by_fy_cat = by_fy_cat.sort_values(["fiscal_year", "category"])

        fig_fy_cat = px.bar(
            by_fy_cat,
            x="fiscal_year",
            y="amount_oku",
            color="category",
            color_discrete_map=CAT_COLOR,
            barmode="stack",
            custom_data=["category"],
            labels={"fiscal_year": "年度", "amount_oku": "金額（億円）", "category": "大項目"},
            template=TEMPLATE,
            title="年度別・大項目別 契約金額",
            category_orders={"category": CAT_ORDER},
        )
        fig_fy_cat.update_layout(
            height=400,
            xaxis=dict(tickmode="linear", dtick=1),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        sel_fy_cat = st.plotly_chart(
            fig_fy_cat, use_container_width=True, on_select="rerun", key="fig_fy_cat"
        )
        st.caption("(クリックでドリルダウン)")
        pts_fy_cat = _pts(sel_fy_cat)
        if pts_fy_cat:
            pt = pts_fy_cat[0]
            fy_sel = int(pt["x"])
            cat_sel2 = pt.get("customdata", [None])[0]
            sub2 = filt[filt["fiscal_year"] == fy_sel]
            if cat_sel2:
                sub2 = sub2[sub2["category"] == cat_sel2]
                show_dd(sub2, f"FY{fy_sel} ／ {cat_sel2}")
            else:
                show_dd(sub2, f"FY{fy_sel}")

        # ── 集計テーブル ─────────────────────────────────────────
        st.markdown("### 大項目・中項目 集計")
        tbl_sub = (
            filt.groupby(["category", "subcategory"])
            .agg(件数=("id", "count"), 金額=("contract_amount", "sum"))
            .reset_index()
        )
        tbl_sub["category"] = pd.Categorical(tbl_sub["category"], categories=CAT_ORDER, ordered=True)
        tbl_sub = tbl_sub.sort_values(["category", "金額"], ascending=[True, False])
        tbl_sub["金額（億円）"] = (tbl_sub["金額"] / 1e8).map("{:,.1f}".format)
        st.dataframe(
            tbl_sub.rename(columns={"category": "大項目", "subcategory": "中項目"})
            [["大項目", "中項目", "件数", "金額（億円）"]],
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
