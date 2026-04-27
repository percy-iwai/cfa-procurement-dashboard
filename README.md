# こども家庭庁 調達DB ダッシュボード

こども家庭庁（Children and Families Agency）の調達情報をビジュアライズするStreamlitダッシュボードです。

## データ

- **期間**: FY2023 (令和5年度) 〜 FY2025 (令和7年度・途中)
- **件数**: 557件 / **総額**: 382.7億円
- **ソース**: [こども家庭庁 契約締結状況](https://www.cfa.go.jp/procurement/proper-public-procurement/)

## 機能

- KPIカード（総金額・件数・随意契約率）
- 年度別・入札方式別トレンド
- 担当部局別分析
- ベンダー上位ランキング
- 入札方式構成比（円グラフ）
- 全件検索テーブル

## ローカル実行

```bash
pip install -r requirements.txt
streamlit run app.py
```
