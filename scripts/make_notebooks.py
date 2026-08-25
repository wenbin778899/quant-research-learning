# -*- coding: utf-8 -*-
"""
make_notebooks.py — 生成 7 本可运行教学 Notebook（notebooks/01-07）

每本 notebook 从 data/csv/ 读入原始数据，独立重算网页图表对应的分析结果，
末 cell 用 np.allclose 与 data/*.json 对照并打印 PASS——证明网页数据可复现。

用法：python make_notebooks.py
"""
import json
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks"
OUT.mkdir(exist_ok=True)

MD, CODE = "markdown", "code"


def md(text): return nbf.v4.new_markdown_cell(text)


def code(text): return nbf.v4.new_code_cell(text)


def new_nb(title, cells):
    nb = nbf.v4.new_notebook()
    nb.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.metadata.language_info = {"name": "python", "version": "3"}
    nb.cells = [md(f"# {title}\n\n> 本 notebook 是《量化研究入门学习资料》第 X 章的可运行配套。\n> 数据源：`data/csv/`。运行前请先执行 `python scripts/generate_data.py` 生成数据。")] + cells
    return nb


# ============================================================================
# 01 数据清洗与复权
# ============================================================================
nb01 = new_nb("01 · 数据获取与清洗", [
    md("""## 目标
从 `data/csv/prices.csv` 出发，完成与网页第 1 章一致的清洗管道（去重 → 前向填充 → 剔除退市后区间），并独立实现前/后复权算法。"""),
    code("""import pandas as pd, numpy as np

prices = pd.read_csv("data/csv/prices.csv", parse_dates=["date"])
basic = pd.read_csv("data/csv/stocks_basic.csv", parse_dates=["delist_date"])
dividends = pd.read_csv("data/csv/dividends.csv", parse_dates=["ex_date"])
print(f"原始 {len(prices):,} 行 × {prices['code'].nunique()} 只股票")"""),
    code("""def clean_pipeline(df, basic):
    \"\"\"清洗：去重 → 排序 → close 前向填充 → 剔除退市日之后的记录\"\"\"
    df = df.drop_duplicates(["code", "date"], keep="last")
    df = df.sort_values(["code", "date"])
    df["close"] = df.groupby("code")["close"].ffill()          # 缺失值前向填充
    for _, r in basic.dropna(subset=["delist_date"]).iterrows():
        df = df.drop(df[(df["code"] == r["code"]) &
                        (df["date"] > r["delist_date"])].index)  # 退市后无数据
    return df

clean = clean_pipeline(prices, basic)
n_miss = int(clean["close"].isna().sum())
print(f"清洗后 {len(clean):,} 行；close 残留缺失 {n_miss} 行（应为 0）")
assert n_miss == 0, "清洗后不应残留缺失"

# 退市股校验：000180/000185/000190 最后记录日 == delist_date 前一日
for _, r in basic.dropna(subset=["delist_date"]).iterrows():
    last = clean[clean["code"] == r["code"]]["date"].max()
    print(f"  {r['code']} 最后数据日 {last.date()}（退市日 {r['delist_date'].date()}）")"""),
    code("""# 停牌与缺失统计（与网页 C5a 对照）
print("close 缺失率(原始):", round(float(prices["close"].isna().mean()), 4))
print("停牌比例:", round(float(clean["is_suspended"].mean()), 4))"""),
    code("""# ---- 复权计算（与生成脚本同款算法）----
df = clean.merge(dividends.rename(columns={"ex_date": "date"}),
                 on=["code", "date"], how="left")
df["cash"] = df["cash"].fillna(0.0)
df["bonus"] = df["bonus"].fillna(0.0)
df = df.sort_values(["code", "date"])
df["prev_close"] = df.groupby("code")["close"].shift(1)
# 除息日复权收益：(close + cash) × (1 + bonus) / prev_close − 1
df["r_adj"] = np.where(df["prev_close"].notna(),
                       (df["close"] + df["cash"]) * (1 + df["bonus"]) / df["prev_close"] - 1,
                       np.nan)
df["cum"] = df.groupby("code")["r_adj"].transform(lambda s: (1 + s.fillna(0)).cumprod())
df["adj_bwd"] = df["close"] * df["cum"]
last_close = df.groupby("code")["close"].transform("last")
last_bwd = df.groupby("code")["adj_bwd"].transform("last")
df["adj_fwd"] = df["adj_bwd"] * (last_close / last_bwd)

# 复权价合理性：除息日（cash>0 或 bonus>0）后复权收益应无跳空
sample = df[df["cash"] > 0].iloc[:1]
print("复权价计算完成 ✓ 前/后复权列已生成，见 df['adj_fwd'] / df['adj_bwd']")"""),
    code("""# ---- 一致性校验 ----
# 与 data/csv/prices.csv 的预计算复权列对照（round 2 位精度）
both = df.merge(clean[["code", "date", "adj_close_fwd", "adj_close_bwd"]],
                on=["code", "date"], suffixes=("", "_ref"))
ok_fwd = np.allclose(both["adj_fwd"].fillna(-1), both["adj_close_fwd"].fillna(-1), atol=0.011)
ok_bwd = np.allclose(both["adj_bwd"].fillna(-1), both["adj_close_bwd"].fillna(-1), atol=0.011)
print("前复权对照:", "PASS" if ok_fwd else "FAIL")
print("后复权对照:", "PASS" if ok_bwd else "FAIL")
assert ok_fwd and ok_bwd"""),
])


# ============================================================================
# 02 因子构建与预处理
# ============================================================================
nb02 = new_nb("02 · 因子构建与预处理", [
    md("""## 目标
从清洗后的价格矩阵重算价格类因子（MOM60/REV5/VOL20），从 `stocks_basic.csv` 计算规模与估值因子，并对全部 8 个因子跑「去极值 → 行业中性化 → z-score」管道，与 `data/csv/factors.csv` 的 z 列对照。

> 注：ROE/GROW/TURN 属于基本面/另类数据，教学上直接采用数据文件中的原始值（获取这类数据本身不是本章重点）。"""),
    code("""import pandas as pd, numpy as np

prices = pd.read_csv("data/csv/prices.csv", parse_dates=["date"])
basic = pd.read_csv("data/csv/stocks_basic.csv", parse_dates=["delist_date"])
factors = pd.read_csv("data/csv/factors.csv", parse_dates=["date"])

# 清洗 → 宽表（date × code）
df = prices.drop_duplicates(["code", "date"]).sort_values(["code", "date"])
df["close"] = df.groupby("code")["close"].ffill()
for _, r in basic.dropna(subset=["delist_date"]).iterrows():
    df = df.drop(df[(df["code"] == r["code"]) & (df["date"] > r["delist_date"])].index)
close = df.pivot(index="date", columns="code", values="close")
close.index = pd.to_datetime(close.index)

INDUSTRIES = ["银行", "非银金融", "医药生物", "电子", "食品饮料",
              "机械设备", "汽车", "电力公用"]
rebal = factors.groupby("date")["code"].count().index      # 60 个调仓日"""),
    code("""# ---- 因子原始值重算 ----
codes = list(close.columns)
shares = basic.set_index("code").loc[codes, "shares"].values
bvps = basic.set_index("code").loc[codes, "bvps"].values
ind_map = dict(zip(basic["code"], basic["industry"]))

rows = []
for d0 in rebal:
    i0 = close.index.get_loc(d0)
    px = close.iloc[i0].values
    px_60 = close.iloc[max(0, i0 - 60)].values
    px_5 = close.iloc[max(0, i0 - 5)].values
    vol20 = -close.iloc[max(0, i0 - 20):i0].values.std(axis=0)   # ddof=0，与生成脚本一致
    mom60 = px / px_60 - 1
    rev5 = -(px / px_5 - 1)
    size = np.log(np.where(px > 0, px * shares, np.nan))
    rows.append({"date": d0, "code": codes,
                 "MOM60": mom60, "REV5": rev5, "VOL20": vol20, "SIZE": size})
long = pd.concat([pd.DataFrame({**{"date": r["date"], "code": r["code"]},
                                **{k: v for k, v in r.items() if k not in ("date", "code")}})
                  for r in rows], ignore_index=True)
# 对照 factors.csv 的价格类因子原始值
for col in ["MOM60", "REV5", "VOL20", "SIZE"]:
    ref = factors[["date", "code", col]].merge(long, on=["date", "code"], suffixes=("", "_r"))
    ok = np.allclose(ref[col].fillna(0), ref[col + "_r"].fillna(0), atol=1e-6)
    print(f"{col:6s} 重算对照: {'PASS' if ok else 'FAIL'}")"""),
    code("""# ---- 预处理管道：winsorize → 行业中性化 → z-score ----
def factor_pipeline(z_mat, industries):
    \"\"\"与生成脚本同款管道（教学版，逐期截面处理）\"\"\"
    T, S = z_mat.shape
    out = np.full_like(z_mat, np.nan)
    dum = pd.get_dummies(industries).values.astype(float)
    X = np.column_stack([np.ones(S), dum[:, :-1]])
    for t in range(T):
        x = z_mat[t]; m = np.isfinite(x)
        if m.sum() < 10: continue
        xm, sd = x[m].mean(), x[m].std()
        if sd == 0 or not np.isfinite(sd): continue
        xw = np.clip(x, xm - 3 * sd, xm + 3 * sd)             # 去极值
        beta, *_ = np.linalg.lstsq(X[m], xw[m], rcond=None)
        resid = xw - X @ beta                                 # 行业中性化
        r = resid[m].std()
        if r == 0 or not np.isfinite(r): continue
        out[t] = (resid - resid[m].mean()) / r                # z-score
    return out

inds = np.array([ind_map[c] for c in codes])
z_ok = {}
for col in ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]:
    # 原始值：价格类用重算结果，基本面类用 factors.csv
    if col in ("MOM60", "REV5", "VOL20", "SIZE"):
        raw = long.pivot(index="date", columns="code", values=col).reindex(rebal).values
    else:
        raw = factors.pivot(index="date", columns="code", values=col).values
    z_calc = factor_pipeline(raw, inds)
    z_ref = factors.pivot(index="date", columns="code", values="z_" + col).values
    same = (np.isnan(z_calc) == np.isnan(z_ref))
    ok = same.all() and np.allclose(np.nan_to_num(z_calc), np.nan_to_num(z_ref), atol=1e-4)
    z_ok[col] = ok
    print(f"z_{col:6s} 管道重算对照: {'PASS' if ok else 'FAIL'}")
assert all(z_ok.values()), "存在不一致的因子" """),
])


# ============================================================================
# 03 因子检验（IC + 分层）
# ============================================================================
nb03 = new_nb("03 · 因子检验：IC 分析与分层回测", [
    md("""## 目标
从 `factors.csv` 重算：月度 IC / Rank IC / ICIR / t 值（对照 `ic.json`）与十分位分层净值（对照 `layers.json`）。"""),
    code("""import pandas as pd, numpy as np
import json

factors = pd.read_csv("data/csv/factors.csv", parse_dates=["date"])
FACTORS = ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]

# ---- 月度 IC / Rank IC ----
def measure_ic(factors):
    ic, ric = {f: [] for f in FACTORS}, {f: [] for f in FACTORS}
    for _, g in factors.groupby("date"):
        y = g["next_return"]
        for f in FACTORS:
            x = g["z_" + f]
            m = x.notna() & y.notna()
            if m.sum() >= 10:
                ic[f].append(np.corrcoef(x[m], y[m])[0, 1])
                ric[f].append(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman"))
    summ = {}
    for f in FACTORS:
        a = np.array(ic[f]); sd = a.std() if len(a) > 1 else 0
        summ[f] = dict(mean=float(a.mean()), std=float(sd),
                       icir=float(a.mean() / sd) if sd else None,
                       t=float(a.mean() / (sd / np.sqrt(len(a)))) if sd else None)
    return ic, ric, summ

ic, ric, summ = measure_ic(factors)
for f in FACTORS:
    print(f"{f:6s} IC={summ[f]['mean']:+.4f}  ICIR={summ[f]['icir']:.3f}  t={summ[f]['t']:6.2f}")"""),
    code("""# ---- 对照 ic.json ----
ref = json.load(open("data/ic.json", encoding="utf-8"))
ok_ic = all(np.allclose(np.array(ic[f]), np.array(ref["ic"][f]), atol=1e-5) for f in FACTORS)
ok_s = all(abs(summ[f]["mean"] - ref["summary"][f]["mean"]) < 5e-5 for f in FACTORS)
print("IC 序列对照:", "PASS" if ok_ic else "FAIL")
print("IC 均值对照:", "PASS" if ok_s else "FAIL")
assert ok_ic and ok_s"""),
    code("""# ---- 十分位分层 ----
def build_layers(factors):
    dates = sorted(factors["date"].unique())
    res = {}
    for f in FACTORS:
        nav = {f"L{k}": [1.0] for k in range(1, 11)}
        ls, monthly = [1.0], {f"L{k}": [] for k in range(1, 11)}
        for _, g in factors.groupby("date"):
            x, y = g["z_" + f], g["next_return"]
            m = x.notna() & y.notna()
            if m.sum() < 20:
                for k in range(1, 11):
                    nav[f"L{k}"].append(nav[f"L{k}"][-1]); monthly[f"L{k}"].append(np.nan)
                ls.append(ls[-1]); continue
            q = pd.qcut(x[m], 10, labels=False, duplicates="drop")
            for k in range(10):
                r = float(y[m][q == k].mean())
                if not np.isfinite(r): r = 0.0    # 空层（分层退化）按收益 0 处理
                monthly[f"L{k+1}"].append(r)
                nav[f"L{k+1}"].append(nav[f"L{k+1}"][-1] * (1 + r))
            ls.append(ls[-1] * (1 + monthly["L10"][-1] - monthly["L1"][-1]))
        res[f] = {**{k: v for k, v in nav.items()}, "LS": ls}
    return res

layers = build_layers(factors)
ref_l = json.load(open("data/layers.json", encoding="utf-8"))
ok_l = all(np.allclose(np.array(layers[f][f"L{k}"][1:]), np.array(ref_l["nav"][f][f"L{k}"][1:]), atol=1e-5)
           for f in FACTORS for k in range(1, 11))
print("分层净值对照:", "PASS" if ok_l else "FAIL")
assert ok_l
print("\\nEP 分层多空累计收益:", round(layers["EP"]["LS"][-1], 3))"""),
])


# ============================================================================
# 04 因子合成
# ============================================================================
nb04 = new_nb("04 · 因子合成", [
    md("""## 目标
重算因子相关矩阵、三种权重方案与合成前后 IC，对照 `combine.json`。"""),
    code("""import pandas as pd, numpy as np, json
factors = pd.read_csv("data/csv/factors.csv", parse_dates=["date"])
FACTORS = ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]

# ---- 相关矩阵（逐期平均）----
corr_pool = []
for _, g in factors.groupby("date"):
    z = g[[f"z_{f}" for f in FACTORS]].dropna()
    if len(z) >= 50: corr_pool.append(z.corr().values)
corr = np.nanmean(np.array(corr_pool), axis=0)
print("MOM60 × REV5 相关:", round(corr[2, 3], 3), "（动量与反转天然负相关）")

# ---- IC 向量与三种权重 ----
def ic_means(factors):
    out = {}
    for f in FACTORS:
        ics = []
        for _, g in factors.groupby("date"):
            x, y = g["z_" + f], g["next_return"]
            m = x.notna() & y.notna()
            if m.sum() >= 10: ics.append(np.corrcoef(x[m], y[m])[0, 1])
        a = np.array(ics); out[f] = dict(mean=a.mean(), icir=a.mean() / a.std())
    return out

icm = ic_means(factors)
ic_vec = np.array([icm[f]["mean"] for f in FACTORS])
icir = np.nan_to_num(np.array([icm[f]["icir"] for f in FACTORS]))
w_equal = np.full(8, 1 / 8)
w_ic = ic_vec / ic_vec.sum()
w_ir = np.clip(icir, 0, None); w_ir = w_ir / w_ir.sum() if w_ir.sum() > 0 else w_equal

# ---- 合成因子 IC ----
def comp_ic(w):
    out = []
    for _, g in factors.groupby("date"):
        z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
        y = g["next_return"]
        m = y.notna() & np.isfinite(z)
        if m.sum() >= 20: out.append(np.corrcoef(z[m], y[m])[0, 1])
    return float(np.mean(out))

print("等权合成 IC:", round(comp_ic(w_equal), 4), "（高于任何单因子——分散化红利）")
print("IC 加权合成 IC:", round(comp_ic(w_ic), 4))
print("IR 加权合成 IC:", round(comp_ic(w_ir), 4))"""),
    code("""# ---- 对照 combine.json ----
ref = json.load(open("data/combine.json", encoding="utf-8"))
ok_corr = np.allclose(corr, np.array(ref["corr"]), atol=1e-4)
ok_w = (np.allclose(w_ic, ref["weights"]["ic"], atol=1e-3)
        and np.allclose(w_ir, ref["weights"]["ir"], atol=1e-3))
ok_ic = abs(comp_ic(w_equal) - ref["ic_compare"]["equal"]) < 1e-3
print("相关矩阵对照:", "PASS" if ok_corr else "FAIL")
print("权重对照:", "PASS" if ok_w else "FAIL")
print("合成 IC 对照:", "PASS" if ok_ic else "FAIL")
assert ok_corr and ok_w and ok_ic"""),
])


# ============================================================================
# 05 组合构建
# ============================================================================
nb05 = new_nb("05 · 组合构建", [
    md("""## 目标
用等权合成因子构建 Top20 等权组合，重算净值/换手/成本敏感性，对照 `portfolio.json`。"""),
    code("""import pandas as pd, numpy as np, json
factors = pd.read_csv("data/csv/factors.csv", parse_dates=["date"])
FACTORS = ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]
w = np.full(8, 1 / 8)

# ---- 逐期 Top20 等权组合 ----
nav, bench, ls, turnover = [1.0], [1.0], [1.0], []
prev = None
for _, g in factors.groupby("date"):
    z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
    y = g["next_return"].values
    if np.isnan(y).all():
        nav.append(nav[-1]); bench.append(bench[-1]); ls.append(ls[-1]); turnover.append(0.0); continue
    order = np.argsort(-z)
    order = order[y[order] == y[order]]          # 剔除退市/无标签
    top, bot = order[:20], order[-20:]
    rp, rb = y[top].mean(), np.nanmean(y)
    nav.append(nav[-1] * (1 + rp)); bench.append(bench[-1] * (1 + rb))
    ls.append(ls[-1] * (1 + rp - y[bot].mean()))
    to = len(set(top) - (prev or set())) * 2 / 20
    turnover.append(to if prev is not None else 0.0)
    prev = set(top)

# ---- 成本敏感性（单边 bps）----
nav_costs = {"0": nav[1:]}
for name, c in [("5", 5e-4), ("10", 1e-3), ("20", 2e-3)]:
    v, seq = 1.0, []
    for to in turnover:
        v *= (1 - to * c); seq.append(v)
    nav_costs[name] = seq

print("组合期末净值:", round(nav[-1], 3), "| 基准:", round(bench[-1], 3),
      "| 平均换手:", f"{np.mean(turnover):.0%}")"""),
    code("""# ---- 对照 portfolio.json ----
ref = json.load(open("data/portfolio.json", encoding="utf-8"))
ok_nav = np.allclose(nav[1:], ref["nav"], atol=1e-5)
ok_turn = np.allclose(turnover, ref["turnover"], atol=1e-3)
ok_cost = np.allclose(nav_costs["20"], ref["nav_costs"]["20"], atol=1e-5)
print("净值对照:", "PASS" if ok_nav else "FAIL")
print("换手对照:", "PASS" if ok_turn else "FAIL")
print("成本敏感性对照:", "PASS" if ok_cost else "FAIL")
assert ok_nav and ok_turn and ok_cost"""),
])


# ============================================================================
# 06 回测与评估（含幸存者偏差演示）
# ============================================================================
nb06 = new_nb("06 · 回测与评估", [
    md("""## 目标
重算净值/回撤/绩效指标（对照 `backtest.json`），并演示「删除退市股」造成的幸存者偏差。"""),
    code("""import pandas as pd, numpy as np, json
factors = pd.read_csv("data/csv/factors.csv", parse_dates=["date"])
FACTORS = ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]
w = np.full(8, 1 / 8)

def run_portfolio(factors):
    nav, bench, turnover, prev = [1.0], [1.0], [], None
    for _, g in factors.groupby("date"):
        z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
        y = g["next_return"].values
        if np.isnan(y).all():
            nav.append(nav[-1]); bench.append(bench[-1]); turnover.append(0.0); continue
        order = np.argsort(-z); order = order[y[order] == y[order]]
        top = order[:20]
        nav.append(nav[-1] * (1 + y[top].mean())); bench.append(bench[-1] * (1 + np.nanmean(y)))
        to = len(set(top) - (prev or set())) * 2 / 20
        turnover.append(to if prev is not None else 0.0); prev = set(top)
    return nav, bench

nav, bench = run_portfolio(factors)

def metrics(nav, bench):
    r = pd.Series(nav).pct_change().dropna()
    T = len(r)
    ar = (nav[-1] / nav[0]) ** (12 / T) - 1
    av = r.std() * np.sqrt(12)
    dd = (pd.Series(nav) / pd.Series(nav).cummax() - 1).min()
    br = pd.Series(bench).pct_change().dropna()
    er = r - br
    te = er.std() * np.sqrt(12)
    return dict(annual_return=round(ar, 4), sharpe=round(r.mean() * 12 / av, 3) if av else None,
                max_drawdown=round(dd, 4),
                info_ratio=round(er.mean() * 12 / te, 3) if te else None)

m = metrics(nav[1:], bench[1:])          # 去掉初始值，与生成器 60 点口径一致
print("组合:", {k: v for k, v in m.items()})
print("基准年化:", round((bench[-1]) ** (12 / len(bench)) - 1, 4))"""),
    code("""# ---- 对照 backtest.json ----
ref = json.load(open("data/backtest.json", encoding="utf-8"))
ok_nav = np.allclose(nav[1:], ref["nav"]["portfolio"], atol=1e-5)
ok_m = abs(m["annual_return"] - ref["metrics"]["portfolio"]["annual_return"]) < 5e-4
print("净值对照:", "PASS" if ok_nav else "FAIL")
print("年化收益对照:", "PASS" if ok_m else "FAIL")
assert ok_nav and ok_m"""),
    md("""### 演示：幸存者偏差
把退市股（000180/000185/000190）从样本中删掉再分层——看分层收益如何被高估："""),
    code("""# 删除退市股 vs 保留（分层多空收益对比）
basic = pd.read_csv("data/csv/stocks_basic.csv")
delisted = set(basic.dropna(subset=["delist_date"])["code"])
f_no_surv = factors[~factors["code"].isin(delisted)].copy()

def layer_ls(factors, zcol="z_EP"):
    ls = [1.0]
    for _, g in factors.groupby("date"):
        x, y = g[zcol], g["next_return"]
        m = x.notna() & y.notna()
        if m.sum() < 20: ls.append(ls[-1]); continue
        q = pd.qcut(x[m], 10, labels=False)
        ls.append(ls[-1] * (1 + y[m][q == 9].mean() - y[m][q == 0].mean()))
    return np.array(ls)

ls_full = layer_ls(factors)         # 含退市股（正确口径）
ls_surv = layer_ls(f_no_surv)       # 删除退市股（错误口径）
print(f"EP 多空累计收益：正确口径 {ls_full[-1]:.3f}  vs  删除退市股 {ls_surv[-1]:.3f}")
print(f"幸存者偏差高估：{(ls_surv[-1] / ls_full[-1] - 1):.1%}")"""),
])


# ============================================================================
# 07 绩效归因
# ============================================================================
nb07 = new_nb("07 · 绩效归因", [
    md("""## 目标
重算 Brinson 归因（配置/选股效应）与风格暴露，对照 `attribution.json`。"""),
    code("""import pandas as pd, numpy as np, json
factors = pd.read_csv("data/csv/factors.csv", parse_dates=["date"])
basic = pd.read_csv("data/csv/stocks_basic.csv")
FACTORS = ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]
w = np.full(8, 1 / 8)
INDUSTRIES = ["银行", "非银金融", "医药生物", "电子", "食品饮料",
              "机械设备", "汽车", "电力公用"]
ind_map = dict(zip(basic["code"], basic["industry"]))

# ---- 行业收益 / 组合行业权重 / 基准权重 ----
ind_ret, w_p, w_b, r_p = {k: [] for k in INDUSTRIES}, [], [], []
for _, g in factors.groupby("date"):
    y = g["next_return"].values
    alive = y == y
    if not alive.any():                                  # 最后一期无标签，平走
        for k in INDUSTRIES: ind_ret[k].append(0.0)
        w_p.append(np.zeros(len(INDUSTRIES))); w_b.append(np.zeros(len(INDUSTRIES)))
        r_p.append(0.0); continue
    inds_g = g["code"].map(ind_map).values              # 单期截面行业
    for k in INDUSTRIES:
        mm = (inds_g == k) & alive
        ind_ret[k].append(float(y[mm].mean()) if mm.sum() else 0.0)
    z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
    order = np.argsort(-z); order = order[y[order] == y[order]]
    top = order[:20]
    wp = np.zeros(len(INDUSTRIES)); wb = np.zeros(len(INDUSTRIES))
    for i in top: wp[INDUSTRIES.index(ind_map[g["code"].iloc[i]])] += 1 / 20
    for i in np.where(alive)[0]: wb[INDUSTRIES.index(ind_map[g["code"].iloc[i]])] += 1 / alive.sum()
    w_p.append(wp); w_b.append(wb); r_p.append(float(y[top].mean()))

ir_ = np.array([ind_ret[k] for k in INDUSTRIES]).T
w_p, w_b = np.array(w_p), np.array(w_b)
alloc = (w_p - w_b) * ir_
total = np.array(r_p) - (w_b * ir_).sum(1)
sel = total - alloc.sum(1)

# 季度聚合
ddates = [str(d.date()) for d in factors["date"].unique()]
q = pd.PeriodIndex(ddates, freq="Q")
agg = pd.DataFrame({"alloc": alloc.sum(1), "sel": sel, "total": total}, index=q).groupby(level=0).sum()
print("前 4 季度归因：")
print(agg.head(4).round(4))"""),
    code("""# ---- 对照 attribution.json ----
ref = json.load(open("data/attribution.json", encoding="utf-8"))
ok_a = np.allclose(agg["alloc"].values, ref["brinson"]["allocation"], atol=1e-3)
ok_s = np.allclose(agg["sel"].values, ref["brinson"]["selection"], atol=1e-3)
print("配置效应对照:", "PASS" if ok_a else "FAIL")
print("选股效应对照:", "PASS" if ok_s else "FAIL")
assert ok_a and ok_s

# ---- 风格暴露（组合持仓的因子加权 z）----
style = {f: [] for f in ["SIZE", "MOM60", "VOL20", "EP", "TURN"]}
for _, g in factors.groupby("date"):
    y = g["next_return"].values
    alive = y == y
    if not alive.any():                            # 最后一期无标签，暴露记 0
        for f in style: style[f].append(0.0)
        continue
    z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
    order = np.argsort(-z)
    order = order[alive[order]]                    # 过滤退市/无标签股票
    top = order[:20]
    for f in style: style[f].append(float(g[f"z_{f}"].values[top].mean()))
ok_st = all(np.allclose(np.array(style[f]), ref["style_exposure"][f], atol=1e-3) for f in style)
print("风格暴露对照:", "PASS" if ok_st else "FAIL")
assert ok_st"""),
])


def write(name, nb):
    path = OUT / name
    with open(path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print(f"  ✓ notebooks/{name}")


if __name__ == "__main__":
    print("生成 7 本 notebook：")
    write("01_data_prep.ipynb", nb01)
    write("02_factor_construction.ipynb", nb02)
    write("03_factor_testing.ipynb", nb03)
    write("04_factor_synthesis.ipynb", nb04)
    write("05_portfolio.ipynb", nb05)
    write("06_backtest.ipynb", nb06)
    write("07_attribution.ipynb", nb07)
    print("完成。")
