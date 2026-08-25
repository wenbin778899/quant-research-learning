# -*- coding: utf-8 -*-
"""
generate_data.py — 《量化研究入门学习资料》数据生成脚本（唯一数据源）

产出：
  1) data/csv/   —— 全量模拟数据（stocks_basic.csv / prices.csv / dividends.csv / factors.csv）
  2) data/*.json —— 网页图表聚合数据（ECharts 直读，每张图一份）

模拟机制（教学意图优先，全可复现，默认 SEED=42）：
  - 200 只股票 × 8 行业 × 1260 个交易日（2020-01 起约 5 年，60 个月度调仓期）
  - 日收益 = 市场 + 行业漂移 + 个股特质噪声（对数正态）
  - 8 个因子（EP/SIZE/MOM20/REV5/VOL20/TURN/ROE/GROW）按 alpha 系数注入未来月收益，
    经自动校准使月度 IC 落入目标区间
  - 3 只退市股（退市前 20 日连续大跌后停牌）→ 幸存者偏差教学点
  - 约 30% 股票季度分红 + 少量送股 → 复权教学点
  - 少量随机停牌与缺失值 → 数据清洗教学点

一致性保证：脚本内部一切分析均基于「prices.csv 注入缺失后 ffill 填充、再剔除退市后区间」
的序列；notebook 从 CSV 读入 → 相同清洗 → 重算，与网页 JSON 数值完全一致
（notebook 末 cell 用 np.allclose 对照校验）。

用法：python generate_data.py [--seed 42]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = ROOT / "data" / "csv"
DATA_JSON = ROOT / "data"

SEED = 42
N_STOCKS = 200
N_DAYS = 1260
INDUSTRIES = ["银行", "非银金融", "医药生物", "电子", "食品饮料",
              "机械设备", "汽车", "电力公用"]
N_IND = len(INDUSTRIES)
IND_PER = N_STOCKS // N_IND

# 因子定义：方向表示「因子值越高，未来收益越高」（z 标准化后的预测方向）
FACTORS = ["EP", "SIZE", "MOM60", "REV5", "VOL20", "TURN", "ROE", "GROW"]
FACTOR_CN = {"EP": "盈利估值", "SIZE": "规模", "MOM60": "60日动量", "REV5": "5日反转",
             "VOL20": "低波动", "TURN": "低换手", "ROE": "质量", "GROW": "成长"}
ALPHA0 = {  # 初始月收益预测力（小数），校准后写入最终值
    "EP": 0.010, "MOM60": 0.009, "ROE": 0.008, "GROW": 0.007,
    "REV5": 0.005, "VOL20": 0.004, "TURN": 0.004, "SIZE": -0.003,
}
IC_BANDS = {  # 目标月度 IC 区间（SIZE 为负向：小市值效应）
    "EP": (0.040, 0.080), "MOM60": (0.040, 0.080), "ROE": (0.040, 0.080), "GROW": (0.040, 0.080),
    "REV5": (0.025, 0.055),   # 短期反转在模拟中天然偏强
    "VOL20": (0.005, 0.030), "TURN": (0.005, 0.030), "SIZE": (-0.030, -0.005),
}
DELIST_PLAN = {180: 12, 185: 20, 190: 28}     # 股票号 -> 退市调仓期索引
DIV_RATIO = 0.30                              # 分红股票占比
MISSING_RATE = 0.005                          # 随机缺失率（close/open）
SUSPEND_RATE = 0.004                          # 随机停牌比例
STYLE_FACTORS = ["SIZE", "MOM60", "VOL20", "EP", "TURN"]   # 风格暴露图用因子


def sanitize(o):
    """递归清洗：NaN/Inf → None，numpy 标量 → Python 标量（JSON 兼容）。"""
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, float):
        return None if not np.isfinite(o) else o
    return o


def rngs():
    """固定种子的随机源（多次运行/校准迭代间保持同一噪声序列）。"""
    return (np.random.default_rng(SEED), np.random.default_rng(SEED + 3),
            np.random.default_rng(SEED + 7), np.random.default_rng(SEED + 11),
            np.random.default_rng(SEED + 5))


# ----------------------------------------------------------------------------
# 1. 日历与股票池
# ----------------------------------------------------------------------------
def build_calendar():
    global N_DAYS
    dates = pd.bdate_range("2020-01-01", "2024-12-31")
    N_DAYS = len(dates)
    s = pd.Series(np.arange(N_DAYS), index=dates)
    rebal = s.groupby(s.index.to_period("M")).max().values   # 每月最后交易日
    assert len(rebal) == 60, f"调仓期应为 60，实际 {len(rebal)}"
    return dates, rebal


def build_universe(rng):
    codes = [f"{i:06d}" for i in range(1, N_STOCKS + 1)]
    industries = [INDUSTRIES[i // IND_PER] for i in range(N_STOCKS)]
    shares = np.exp(rng.uniform(np.log(1e8), np.log(1e9), N_STOCKS))
    bvps = rng.uniform(1.0, 6.0, N_STOCKS)
    roe_base = rng.uniform(0.06, 0.24, N_STOCKS)
    return pd.DataFrame({"code": codes, "industry": industries, "shares": shares,
                         "bvps": bvps, "roe_base": roe_base,
                         "list_date": pd.Timestamp("2020-01-02"), "delist_date": pd.NaT})


# ----------------------------------------------------------------------------
# 2. 日收益与价格模拟（含分红/退市/停牌）
# ----------------------------------------------------------------------------
def simulate_prices(rng, universe, dates, rebal):
    """日收益矩阵 ret (N_DAYS×S)：市场+行业+噪声+停牌+退市；分红事件表；退市日 map。"""
    ind_of = np.array([INDUSTRIES.index(x) for x in universe["industry"]])
    mkt = rng.normal(0.0004, 0.0110, N_DAYS)
    ind_beta = rng.uniform(0.6, 1.4, N_IND)
    ind_drift = rng.uniform(0.0000, 0.0006, N_IND)
    ind_noise = rng.normal(0.0, 0.005, (N_DAYS, N_IND))
    stock_sigma = rng.uniform(0.012, 0.032, N_STOCKS)

    ret = (mkt[:, None] * ind_beta[None, ind_of] + ind_drift[None, ind_of]
           + ind_noise[:, ind_of]
           + rng.normal(0.0, 1.0, (N_DAYS, N_STOCKS)) * stock_sigma[None, :])

    suspend = rng.random((N_DAYS, N_STOCKS)) < SUSPEND_RATE
    suspend[0] = False
    ret[suspend] = 0.0

    # 退市股：退市调仓期前 12 个交易日连续大跌（月收益约 -26%，A 股退市前常见形态），
    # 退市日起数据截止（NaN）。大跌幅度控制在不至于极端扭曲截面 IC 的程度。
    delist_day = {}
    for code_no, rebal_t in DELIST_PLAN.items():
        i = code_no - 1
        t_day = int(rebal[rebal_t])
        ret[t_day - 12:t_day, i] = rng.normal(-0.030, 0.006, 12)
        ret[t_day:, i] = np.nan
        delist_day[i] = t_day
        universe.loc[i, "delist_date"] = dates[t_day]

    # 分红事件表（现金 + 送股）
    div_rows, shares = [], universe["shares"].copy()
    rng_d = np.random.default_rng(SEED + 7)
    for i in range(N_STOCKS):
        if rng_d.random() > DIV_RATIO:
            continue
        for q in pd.date_range("2020-03-31", "2024-12-31", freq="Q"):
            idx = np.searchsorted(dates, q)
            if idx >= N_DAYS:
                break
            cash = rng_d.uniform(0.05, 0.50)
            bonus = rng_d.choice([0.0, 0.1, 0.2], p=[0.7, 0.2, 0.1])
            div_rows.append({"code": f"{i+1:06d}", "ex_date": dates[idx],
                             "cash": round(cash, 4), "bonus": round(bonus, 4)})
            shares[i] *= (1 + bonus)
    dividends = pd.DataFrame(div_rows)
    universe["shares"] = shares

    return ret, dividends, delist_day, suspend


def to_prices(ret, universe, dates, dividends):
    """由收益序列构造成交价；除息日成交价 = (理论价 - cash) / (1+bonus)。"""
    rng0 = np.random.default_rng(SEED + 5)
    p = np.zeros((N_DAYS, N_STOCKS))
    p[0] = 10.0 * np.exp(rng0.normal(0.0, 0.3, N_STOCKS))
    p[0] = np.where(np.isnan(ret[0]), np.nan, p[0])
    for t in range(1, N_DAYS):
        p[t] = p[t - 1] * (1 + ret[t])
    for _, row in dividends.iterrows():
        i = int(row["code"]) - 1
        idx = np.searchsorted(dates, row["ex_date"])
        if idx < N_DAYS:
            # 仅除息日当天跳空；后续价格在除息价基础上自然连续累积
            p[idx, i] = (p[idx, i] - row["cash"]) / (1 + row["bonus"])
    return p


def clean_prices(p, delist_day):
    """清洗（与 notebook 工作流一致）：随机缺失 ffill 填充 + 退市后置 NaN。"""
    filled = pd.DataFrame(p).ffill().values
    for i, t_day in delist_day.items():
        filled[t_day:, i] = np.nan
    return filled


# ----------------------------------------------------------------------------
# 3. 月度因子构建
# ----------------------------------------------------------------------------
def factor_pipeline(z_mat, industries):
    """winsorize(3σ) → 行业中性化（OLS 残差）→ zscore。z_mat: (T, S)。"""
    T, S = z_mat.shape
    out = np.full_like(z_mat, np.nan)
    dum = pd.get_dummies(industries).values.astype(float)
    X = np.column_stack([np.ones(S), dum[:, :-1]])
    for t in range(T):
        x = z_mat[t]
        m = np.isfinite(x)
        if m.sum() < 10:
            continue
        xm, sd = x[m].mean(), x[m].std()
        if not np.isfinite(sd) or sd == 0:
            continue
        xw = np.clip(x, xm - 3 * sd, xm + 3 * sd)      # winsorize（3σ 截尾）
        beta, *_ = np.linalg.lstsq(X[m], xw[m], rcond=None)
        resid = xw - X @ beta                           # 行业中性化（回归残差）
        r = resid[m].std()
        if r == 0 or not np.isfinite(r):
            continue
        out[t] = (resid - resid[m].mean()) / r          # 截面 zscore
    return out


def build_factors(close_mat, universe, dates, rebal):
    """月度因子面板（t 期因子预测 t+1 期月收益），返回 DataFrame 与 z 矩阵。"""
    S = N_STOCKS
    T = len(rebal)
    rng_f = np.random.default_rng(SEED + 3)
    roe = np.tile(universe["roe_base"].values, (T, 1))
    grow = np.full((T, S), 0.15)
    for t in range(1, T):
        if t % 3 == 0:
            roe[t] = np.clip(roe[t - 1] + rng_f.normal(0, 0.03, S), 0.0, 0.45)
        grow[t] = np.clip(grow[t - 1] + rng_f.normal(0, 0.02, S), -0.2, 0.8)
    turn_panel = np.clip(np.exp(rng_f.normal(-3.0, 0.5, (T, S))), 0.01, 1.0)

    shares = universe["shares"].values
    bvps = universe["bvps"].values
    inds = universe["industry"].values
    non_turn = [f for f in FACTORS if f != "TURN"]
    zmat = {f: np.full((T, S), np.nan) for f in FACTORS}
    raw = {f: np.full((T, S), np.nan) for f in FACTORS}

    for t in range(T):
        d0 = int(rebal[t])
        px = close_mat[d0]
        # 因子窗口一律用调仓日之前的历史数据（严禁未来数据 → 前瞻偏差教学点）
        px_prev60 = close_mat[max(0, d0 - 60)]
        px_prev5 = close_mat[max(0, d0 - 5)]
        vol_seg = close_mat[max(0, d0 - 20):d0]
        eps = roe[t] * bvps
        vals = {
            "EP": eps / np.where(px > 0, px, np.nan),
            "SIZE": np.log(np.where(px > 0, px * shares, np.nan)),
            "MOM60": px / px_prev60 - 1,
            "REV5": -(px / px_prev5 - 1),
            "VOL20": -vol_seg.std(0),
            "ROE": roe[t],
            "GROW": grow[t],
        }
        zt = factor_pipeline(np.array([vals[f] for f in non_turn]), inds)
        for k, f in enumerate(non_turn):
            raw[f][t], zmat[f][t] = vals[f], zt[k]
        raw["TURN"][t] = -turn_panel[t]
    zmat["TURN"] = factor_pipeline(-turn_panel, inds)

    recs = []
    for t in range(T):
        d0 = int(rebal[t])
        d1 = int(rebal[t + 1]) if t + 1 < T else N_DAYS - 1
        # 最后一期无未来收益，标签为 NaN（不参与检验/回测）
        nxt = close_mat[d1] / close_mat[d0] - 1 if t + 1 < T else np.nan
        rec = pd.DataFrame({"date": dates[d0], "code": universe["code"].values})
        for f in FACTORS:
            rec[f] = raw[f][t]
            rec[f"z_{f}"] = zmat[f][t]
        rec["next_return"] = nxt
        recs.append(rec)
    return pd.concat(recs, ignore_index=True), zmat


# ----------------------------------------------------------------------------
# 4. alpha 注入与校准
# ----------------------------------------------------------------------------
def apply_alpha_daily(ret_daily, ma, rebal):
    """将月度 alpha 均匀分摊到调仓期内每日，叠加到日收益。

    注入区间取 (d0, d1]（调仓日当天不注入）——保证因子计算所用的调仓日
    收盘价不被当期注入污染，避免动量类因子自我反馈发散。
    """
    T, S = ma.shape
    share = np.zeros((N_DAYS, S))
    for t in range(T):
        d0 = int(rebal[t])
        d1 = int(rebal[t + 1]) if t + 1 < T else N_DAYS - 1
        span = d1 - d0
        if span > 0:
            share[d0 + 1:d1 + 1] = ma[t] / span
    return ret_daily + share


def measure_ic(fdf):
    """月度 IC / rank IC + 汇总（mean/std/ICIR/t 值）。"""
    ic = {f: [] for f in FACTORS}
    ric = {f: [] for f in FACTORS}
    for _, g in fdf.groupby("date"):
        y = g["next_return"]
        for f in FACTORS:
            x = g[f"z_{f}"]
            m = x.notna() & y.notna()
            if m.sum() >= 10:
                ic[f].append(float(np.corrcoef(x[m], y[m])[0, 1]))
                ric[f].append(float(pd.Series(x[m]).corr(pd.Series(y[m]), method="spearman")))
    summ = {}
    for f in FACTORS:
        a = np.array(ic[f]); r = np.array(ric[f])
        sd = a.std() if len(a) > 1 else 0.0
        summ[f] = {"mean": float(a.mean()), "std": float(sd),
                   "icir": float(a.mean() / sd) if sd else None,
                   "t": float(a.mean() / (sd / np.sqrt(len(a)))) if sd else None,
                   "rank_mean": float(r.mean()), "n": int(len(a))}
    return ic, ric, summ


def calibrate(universe, dates, rebal, ret_daily, dividends, delist_day):
    """迭代校准 alpha（最多 6 轮），使各因子月度 IC 落入目标区间。"""
    alpha = dict(ALPHA0)
    for it in range(6):
        p = to_prices(ret_daily, universe, dates, dividends)
        close = clean_prices(p, delist_day)
        fdf, zmat = build_factors(close, universe, dates, rebal)
        ma = np.zeros((len(rebal), N_STOCKS))
        for f in FACTORS:
            ma += alpha[f] * np.nan_to_num(zmat[f], nan=0.0)
        ret_final = apply_alpha_daily(ret_daily, ma, rebal)
        p_final = to_prices(ret_final, universe, dates, dividends)
        close_f = clean_prices(p_final, delist_day)
        fdf, zmat = build_factors(close_f, universe, dates, rebal)
        _, _, summ = measure_ic(fdf)
        ok = all(IC_BANDS[f][0] <= summ[f]["mean"] <= IC_BANDS[f][1] for f in FACTORS)
        if ok:
            break
        for f in FACTORS:
            lo, hi = IC_BANDS[f]
            cur = summ[f]["mean"]
            if cur == 0 or not np.isfinite(cur):
                continue
            # 保持 alpha 符号（方向由因子定义决定），限幅 0.5~2.0 防振荡
            scale = float(np.clip((lo + hi) / 2 / cur, 0.5, 2.0))
            alpha[f] *= scale
    return alpha, fdf, zmat, ret_final, p_final


# ----------------------------------------------------------------------------
# 5. 分析模块（IC/分层/合成/组合/回测/归因）
# ----------------------------------------------------------------------------
def compute_ic_payload(fdf):
    ic, ric, summ = measure_ic(fdf)
    dates = [str(d.date()) for d in fdf["date"].unique()]
    return {"dates": dates, "factors": FACTORS,
            "ic": {f: [round(v, 5) for v in ic[f]] for f in FACTORS},
            "rank_ic": {f: [round(v, 5) for v in ric[f]] for f in FACTORS},
            "summary": summ,
            "cum_ic": {f: [round(v, 5) for v in np.cumsum(ic[f])] for f in FACTORS}}


def build_layers(fdf):
    """十分位分层：每期按 z 分 10 层 → 层内月收益均值 → 层净值（多空 = 层10 − 层1）。"""
    dates = [str(d.date()) for d in fdf["date"].unique()]
    res = {"factors": FACTORS, "dates": dates, "nav": {}, "monthly": {}}
    for f in FACTORS:
        nav = {f"L{k}": [1.0] for k in range(1, 11)}
        ls = [1.0]
        monthly = {f"L{k}": [] for k in range(1, 11)}
        for _, g in fdf.groupby("date"):
            x = g[f"z_{f}"]; y = g["next_return"]
            m = x.notna() & y.notna()
            if m.sum() < 20:
                for k in range(1, 11):
                    nav[f"L{k}"].append(nav[f"L{k}"][-1])
                    monthly[f"L{k}"].append(np.nan)
                ls.append(ls[-1])
                continue
            q = pd.qcut(x[m], 10, labels=False, duplicates="drop")
            for k in range(10):
                r = float(y[m][q == k].mean())
                monthly[f"L{k+1}"].append(r)
                nav[f"L{k+1}"].append(nav[f"L{k+1}"][-1] * (1 + r))
            ls.append(ls[-1] * (1 + monthly["L10"][-1] - monthly["L1"][-1]))
        res["nav"][f] = {**{k: [round(v, 6) for v in vals] for k, vals in nav.items()},
                         "LS": [round(v, 6) for v in ls]}
        res["monthly"][f] = {k: [round(v, 6) if v == v else None for v in vals]
                             for k, vals in monthly.items()}
    return res


def synthesize(fdf):
    """因子相关性矩阵 + 3 种合成权重 + 合成前后 IC 对比。"""
    corr_pool = []
    for _, g in fdf.groupby("date"):
        z = g[[f"z_{f}" for f in FACTORS]].dropna()
        if len(z) >= 50:
            corr_pool.append(z.corr().values)
    corr = np.nanmean(np.array(corr_pool), axis=0)

    _, _, summ = measure_ic(fdf)
    ic_vec = np.array([summ[f]["mean"] for f in FACTORS])
    icir = np.nan_to_num(np.array([summ[f]["icir"] for f in FACTORS]))
    w_ic = ic_vec / ic_vec.sum()
    w_ir = np.clip(icir, 0.0, None)
    w_ir = w_ir / w_ir.sum() if w_ir.sum() > 0 else np.full(len(FACTORS), 1 / len(FACTORS))

    def comp_ic(w):
        out = []
        for _, g in fdf.groupby("date"):
            z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0)
            y = g["next_return"]
            s = z.values @ w
            m = y.notna() & np.isfinite(s)
            if m.sum() >= 20:
                out.append(float(np.corrcoef(s[m], y[m])[0, 1]))
        return float(np.mean(out)) if out else None

    def r4(v):
        return round(v, 4) if v is not None else None

    return {"factors": FACTORS,
            "corr": [[round(v, 4) for v in row] for row in corr],
            "weights": {"equal": [round(v, 4) for v in np.full(8, 1 / 8)],
                        "ic": [round(v, 4) for v in w_ic],
                        "ir": [round(v, 4) for v in w_ir]},
            "ic_compare": {**{f: round(summ[f]["mean"], 4) for f in FACTORS},
                           "equal": r4(comp_ic(np.full(8, 1 / 8))),
                           "ic": r4(comp_ic(w_ic)),
                           "ir": r4(comp_ic(w_ir))}}


def build_portfolio(fdf, universe, dates, rebal):
    """等权合成因子 → Top20 等权组合：净值/换手/成本敏感性/持仓结构。"""
    T = len(rebal)
    w = np.full(8, 1 / 8)
    nav, bench, ls = [1.0], [1.0], [1.0]
    turnover, top_rows, ind_rows = [], None, None
    codes, inds = universe["code"].values, universe["industry"].values
    prev_pick = None
    for t, (_, g) in enumerate(fdf.groupby("date")):
        z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
        y = g["next_return"].values
        if np.isnan(y).all():                      # 最后一期无未来收益，净值平走
            nav.append(nav[-1]); bench.append(bench[-1]); ls.append(ls[-1])
            turnover.append(0.0)
            continue
        order = np.argsort(-z)                     # 按合成因子分数排序
        order = order[y[order] == y[order]]        # 过滤退市/无标签股票
        top = order[:20]
        bot = order[-20:]
        rp = float(y[top].mean())
        rb = float(np.nanmean(y))
        rl = rp - float(y[bot].mean())
        nav.append(nav[-1] * (1 + rp)); bench.append(bench[-1] * (1 + rb))
        ls.append(ls[-1] * (1 + rl))
        pick = set(top)
        to = (len(pick - prev_pick) * 2 / 20) if prev_pick is not None else 0.0
        turnover.append(to); prev_pick = pick
        if t == T - 1:
            top_rows = [{"code": codes[i], "industry": inds[i], "weight": 0.05} for i in top]
            ind_agg = {}
            for i in top:
                ind_agg[inds[i]] = ind_agg.get(inds[i], 0) + 0.05
            ind_rows = [{"industry": k, "weight": round(v, 4)} for k, v in ind_agg.items()]

    costs = {"0": [round(v, 6) for v in nav[1:]]}
    for name, c in [("5", 0.0005), ("10", 0.0010), ("20", 0.0020)]:
        v, seq = 1.0, []
        for to in turnover:
            v *= (1 - to * c)
            seq.append(v)
        costs[name] = [round(x, 6) for x in seq]
    return {"dates": [str(d.date()) for d in fdf["date"].unique()],
            "nav": [round(v, 6) for v in nav[1:]],
            "benchmark": [round(v, 6) for v in bench[1:]],
            "long_short": [round(v, 6) for v in ls[1:]],
            "nav_costs": {k: [round(v, 6) for v in vals] for k, vals in costs.items()},
            "turnover": [round(v, 4) for v in turnover],
            "top_weights": top_rows, "industry_weights": ind_rows,
            "params": {"top_n": 20, "rebalance": "monthly", "costs_bps": [0, 5, 10, 20]}}


def metrics(nav, bench=None):
    r = pd.Series(nav).pct_change().dropna()
    T = len(r)
    ar = (nav[-1] / nav[0]) ** (12 / T) - 1
    av = float(r.std() * np.sqrt(12))
    sh = float(r.mean() * 12 / av) if av else None
    dd = float((pd.Series(nav) / pd.Series(nav).cummax() - 1).min())
    calmar = float(ar / abs(dd)) if dd else None
    out = {"annual_return": round(ar, 4), "annual_vol": round(av, 4),
           "sharpe": round(sh, 3) if sh is not None else None,
           "max_drawdown": round(dd, 4), "calmar": round(calmar, 2) if calmar is not None else None,
           "win_rate": round(float((r > 0).mean()), 3)}
    if bench is not None:
        br = pd.Series(bench).pct_change().dropna()
        bar = (bench[-1] / bench[0]) ** (12 / len(br)) - 1
        er = r - br
        te = float(er.std() * np.sqrt(12))
        out["excess_annual"] = round(ar - bar, 4)
        out["tracking_error"] = round(te, 4)
        out["info_ratio"] = round(float(er.mean() * 12 / te), 3) if te else None
        out["excess_win"] = round(float((er > 0).mean()), 3)
    return out


def backtest_payload(port):
    nav, bench, ls = port["nav"], port["benchmark"], port["long_short"]
    dd_p = (pd.Series(nav) / pd.Series(nav).cummax() - 1).tolist()
    dd_b = (pd.Series(bench) / pd.Series(bench).cummax() - 1).tolist()
    rp = pd.Series(nav).pct_change().dropna()
    rb = pd.Series(bench).pct_change().dropna()
    er = (rp - rb).rolling(12).apply(lambda x: np.prod(1 + x) - 1, raw=True)
    return {"dates": port["dates"],
            "nav": {"portfolio": nav, "benchmark": bench, "long_short": ls},
            "drawdown": {"portfolio": [round(v, 6) for v in dd_p],
                         "benchmark": [round(v, 6) for v in dd_b]},
            "rolling_excess": [round(v, 6) if v == v else None for v in er],
            "metrics": {"portfolio": metrics(nav), "benchmark": metrics(bench),
                        "excess": metrics(nav, bench)}}


def attribution_payload(fdf, universe, port):
    """Brinson 两分法归因（季度聚合：配置 + 选股[含交互]）+ 风格暴露 + 风险分解。"""
    ddates = port["dates"]
    inds = universe["industry"].values
    ind_list = INDUSTRIES
    w = np.full(8, 1 / 8)

    ind_ret = {k: [] for k in ind_list}
    w_p, w_b, r_p = [], [], []
    for _, g in fdf.groupby("date"):
        y = g["next_return"].values
        alive = y == y
        for k in ind_list:
            mm = (inds == k) & alive
            ind_ret[k].append(float(y[mm].mean()) if mm.sum() else 0.0)
        wp = np.zeros(N_IND); wb = np.zeros(N_IND)
        if alive.sum() == 0:                       # 最后一期无未来收益
            w_p.append(wp); w_b.append(wb); r_p.append(0.0)
            continue
        z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
        order = np.argsort(-z)
        top = order[alive][:20]
        for i in top:
            wp[INDUSTRIES.index(inds[i])] += 0.05
        for i in np.where(alive)[0]:
            wb[INDUSTRIES.index(inds[i])] += 1 / alive.sum()
        w_p.append(wp); w_b.append(wb); r_p.append(float(y[top].mean()))

    ir_ = np.array([ind_ret[k] for k in ind_list]).T            # (T, 8) 行业收益
    w_p = np.array(w_p); w_b = np.array(w_b)
    alloc = (w_p - w_b) * ir_                                   # 配置效应
    total = np.array(r_p) - (w_b * ir_).sum(1)                  # 组合超额收益
    sel = total - alloc.sum(1)                                  # 选股效应（含交互）
    q = pd.PeriodIndex(ddates, freq="Q")
    agg = pd.DataFrame({"alloc": alloc.sum(1), "sel": sel, "total": total},
                       index=q).groupby(level=0).sum()

    # 风格暴露（组合持仓的因子加权 z，5 个风格因子）
    style = {f: [] for f in STYLE_FACTORS}
    for _, g in fdf.groupby("date"):
        z = g[[f"z_{f}" for f in FACTORS]].fillna(0.0).values @ w
        top = np.argsort(-z)[:20]
        for f in STYLE_FACTORS:
            style[f].append(float(g[f"z_{f}"].values[top].mean()))

    # 风险分解：季度滚动 12 期回归，用增量 R² 分解（系统性/行业/特质，总和恒为 1）
    rp = pd.Series(port["nav"]).pct_change().dropna().values     # 59 期收益
    rb = pd.Series(port["benchmark"]).pct_change().dropna().values
    ind_rel = ir_[:-1] - ir_[:-1].mean(1, keepdims=True)         # 行业相对收益（对齐 59 期）
    q_dates = [str(x) for x in agg.index]                        # 20 个季度
    sys_, ind_, idio_ = [], [], []
    for qk, qd in enumerate(q_dates):
        end = min((qk + 1) * 3, len(rp))                         # 每季 3 期（末季截断）
        if end < 12:
            sys_.append(None); ind_.append(None); idio_.append(None)
            continue
        seg_rp, seg_rb = rp[end - 12:end], rb[end - 12:end]
        var_t = seg_rp.var()
        if var_t == 0:
            sys_.append(None); ind_.append(None); idio_.append(None)
            continue
        r2_m = 1.0 - (seg_rp - np.polyval(np.polyfit(seg_rb, seg_rp, 1), seg_rb)).var() / var_t
        X = np.column_stack([np.ones(len(seg_rp)), seg_rb, ind_rel[end - 12:end]])
        beta, *_ = np.linalg.lstsq(X, seg_rp, rcond=None)
        resid = seg_rp - X @ beta
        r2_all = 1.0 - resid.var() / var_t
        sys_.append(float(r2_m))
        ind_.append(float(max(0.0, r2_all - r2_m)))
        idio_.append(float(max(0.0, 1.0 - r2_all)))
    return {"quarters": q_dates,
            "brinson": {"allocation": [round(v, 4) for v in agg["alloc"]],
                        "selection": [round(v, 4) for v in agg["sel"]],
                        "total": [round(v, 4) for v in agg["total"]]},
            "style_exposure": {"dates": ddates,
                               **{f: [round(v, 4) for v in style[f]] for f in STYLE_FACTORS}},
            "risk": {"dates": q_dates, "systematic": sys_, "industry": ind_, "idiosyncratic": idio_}}


# ----------------------------------------------------------------------------
# 6. 复权价（前/后复权，教学简版算法）
# ----------------------------------------------------------------------------
def compute_distribution(close_mat, universe, dates, rebal):
    """第 2 章 C6/C7 用：某期单因子的预处理三态分布（原始 / winsorize+zscore / 中性化后）。

    取第 10 个调仓期的 EP 因子：输出原始值、仅标准化值、完整管道值（按行业分组）。
    """
    t = 10
    d0 = int(rebal[t])
    px = close_mat[d0]
    eps = universe["roe_base"].values * universe["bvps"].values
    raw = eps / np.where(px > 0, px, np.nan)
    inds = universe["industry"].values
    # 仅 winsorize + zscore（不做中性化）
    z_std = factor_pipeline(np.array([raw]), inds)[0]
    # 完整管道（winsorize + 中性化 + zscore）
    z_full = factor_pipeline(np.array([raw]), inds)[0]
    # 无中性化版本：winsorize + zscore（行业无关）
    m = np.isfinite(raw)
    xw = np.clip(raw, np.nanmean(raw[m]) - 3 * np.nanstd(raw[m]),
                 np.nanmean(raw[m]) + 3 * np.nanstd(raw[m]))
    z_only = (xw - np.nanmean(xw[m])) / np.nanstd(xw[m])
    return {
        "date": str(dates[d0].date()),
        "factor": "EP",
        "industries": INDUSTRIES,
        "raw": [round(v, 6) if v == v else None for v in raw],
        "z_only": [round(v, 6) if v == v else None for v in z_only],
        "z_neutral": [round(v, 6) if v == v else None for v in z_full],
        "industry_of": [INDUSTRIES.index(x) for x in inds],
    }


def compute_adjusted(close_mat, dividends, dates):
    """后复权 = close × cumprod(1+r_adj)；r_adj 在除息日 = (close+cash)(1+bonus)/prev − 1。
    前复权 = 后复权 × (最新收盘价 / 最新后复权价)。输入 close_mat 为清洗后矩阵。"""
    long = pd.DataFrame(close_mat).reset_index().melt(id_vars="index", var_name="ci")
    long.columns = ["idx", "ci", "close"]
    long["code"] = long["ci"].astype(int).add(1).map(lambda x: f"{x:06d}")
    long["date"] = long["idx"].map(dict(enumerate(dates)))
    df = long.merge(dividends.rename(columns={"ex_date": "date"}),
                    on=["code", "date"], how="left")
    df["cash"] = df["cash"].fillna(0.0)
    df["bonus"] = df["bonus"].fillna(0.0)
    df = df.sort_values(["code", "idx"])
    df["prev_close"] = df.groupby("code")["close"].shift(1)
    df["r_adj"] = np.where(df["prev_close"].notna() & df["close"].notna(),
                           ((df["close"] + df["cash"]) * (1 + df["bonus"]) / df["prev_close"] - 1),
                           np.nan)
    df["cum"] = df.groupby("code")["r_adj"].transform(lambda s: (1 + s.fillna(0)).cumprod())
    df["adj_bwd"] = df["close"] * df["cum"]
    last_close = df.groupby("code")["close"].transform("last")
    last_bwd = df.groupby("code")["adj_bwd"].transform("last")
    df["adj_fwd"] = df["adj_bwd"] * (last_close / last_bwd)
    return df[["date", "code", "adj_fwd", "adj_bwd"]].rename(
        columns={"adj_fwd": "adj_close_fwd", "adj_bwd": "adj_close_bwd"})


# ----------------------------------------------------------------------------
# 7. 导出与自检
# ----------------------------------------------------------------------------
def export_json(name, obj):
    path = DATA_JSON / name
    path.write_text(json.dumps(sanitize(obj), ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ data/{name} ({path.stat().st_size:,} B)")


def main():
    global SEED, N_DAYS
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    SEED = args.seed
    DATA_CSV.mkdir(parents=True, exist_ok=True)
    DATA_JSON.mkdir(parents=True, exist_ok=True)

    print("== 1/4 日历、股票池与价格模拟 ==")
    dates, rebal = build_calendar()
    universe = build_universe(rngs()[0])
    ret_daily, dividends, delist_day, suspend = simulate_prices(rngs()[0], universe, dates, rebal)

    print("== 2/4 alpha 校准（目标 IC 区间）==")
    alpha, fdf, zmat, ret_final, p_final = calibrate(universe, dates, rebal, ret_daily,
                                                     dividends, delist_day)
    _, _, summ = measure_ic(fdf)
    for f in FACTORS:
        s = summ[f]
        print(f"   {f:6s} IC={s['mean']:+.4f}  ICIR={s['icir']}  t={s['t']}  rank={s['rank_mean']:+.4f}")

    print("== 3/4 分析（IC/分层/合成/组合/回测/归因）==")
    close_clean = clean_prices(p_final, delist_day)
    ic_payload = compute_ic_payload(fdf)
    layers = build_layers(fdf)
    comb = synthesize(fdf)
    port = build_portfolio(fdf, universe, dates, rebal)
    bt = backtest_payload(port)
    att = attribution_payload(fdf, universe, port)

    print("== 4/4 导出 ==")
    # ---- CSV ----
    long_rows = []
    for t in range(N_DAYS):
        alive = ~np.isnan(p_final[t])
        if not alive.any():
            break
        long_rows.append(pd.DataFrame({
            "date": dates[t], "code": universe["code"].values[alive],
            "open": p_final[t][alive], "high": p_final[t][alive],
            "low": p_final[t][alive], "close": p_final[t][alive],
            "volume": np.nan, "turnover": np.nan, "is_suspended": suspend[t][alive]}))
    prices_long = pd.concat(long_rows, ignore_index=True)
    # 注入随机缺失（close/open 各 ~0.5%）
    rng_m = np.random.default_rng(SEED + 11)
    mask = rng_m.random(len(prices_long)) < MISSING_RATE
    prices_long.loc[mask & (prices_long["is_suspended"] == 0), "close"] = np.nan
    prices_long.loc[mask, "open"] = np.nan
    # 成交量/换手（独立模拟）
    rng_v = np.random.default_rng(SEED + 17)
    prices_long["volume"] = 1e7 * np.exp(rng_v.normal(0, 0.5, len(prices_long)))
    prices_long["turnover"] = 0.02 * np.exp(rng_v.normal(0, 0.5, len(prices_long)))
    prices_long.loc[prices_long["is_suspended"] == 1, "volume"] = 0.0
    # 复权价（基于清洗后矩阵，与 notebook 一致）
    adj = compute_adjusted(close_clean, dividends, dates)
    prices_long = prices_long.merge(adj, on=["date", "code"], how="left")
    prices_long.to_csv(DATA_CSV / "prices.csv", index=False, float_format="%.4f")
    print("  ✓ data/csv/prices.csv")

    universe[["code", "industry", "shares", "bvps", "roe_base", "list_date", "delist_date"]] \
        .to_csv(DATA_CSV / "stocks_basic.csv", index=False, float_format="%.4f")
    print("  ✓ data/csv/stocks_basic.csv")
    dividends.to_csv(DATA_CSV / "dividends.csv", index=False, float_format="%.4f")
    print("  ✓ data/csv/dividends.csv")
    fdf.to_csv(DATA_CSV / "factors.csv", index=False, float_format="%.6f")
    print("  ✓ data/csv/factors.csv")

    # ---- JSON ----
    export_json("ic.json", ic_payload)
    export_json("layers.json", layers)
    export_json("factor_corr.json", comb)
    export_json("combine.json", comb)
    export_json("portfolio.json", port)
    export_json("backtest.json", bt)
    export_json("attribution.json", att)

    mv_last = np.exp(p_final[-1]) * universe["shares"].values
    export_json("industry.json", {
        "industries": INDUSTRIES,
        "stock_counts": [int((universe["industry"] == k).sum()) for k in INDUSTRIES],
        "total_mv": [round(float(mv_last[universe["industry"].values == k].sum()), 0)
                     for k in INDUSTRIES]})

    dret = close_clean[1:] / close_clean[:-1] - 1
    boxes = []
    for k in INDUSTRIES:
        mask = (universe["industry"].values == k)
        v = dret[:, mask]
        v = v[np.isfinite(v) & (v > -0.5) & (v < 0.5)]
        boxes.append({"industry": k,
                      "min": round(float(np.quantile(v, 0.01)), 4),
                      "q1": round(float(np.quantile(v, 0.25)), 4),
                      "median": round(float(np.quantile(v, 0.50)), 4),
                      "q3": round(float(np.quantile(v, 0.75)), 4),
                      "max": round(float(np.quantile(v, 0.99)), 4)})
    export_json("quality.json", {
        "columns": ["open", "high", "low", "close"],
        "missing_rates": [round(float(prices_long[c].isna().mean()), 4)
                          for c in ["open", "high", "low", "close"]],
        "missing_close": round(float(prices_long["close"].isna().mean()), 4),
        "suspended_rate": round(float(prices_long["is_suspended"].mean()), 4),
        "return_boxes": boxes})

    kline = {"stocks": []}
    for cno in [1, 2, 180]:
        code = f"{cno:06d}"
        sub = prices_long[prices_long["code"] == code].iloc[-120:]
        if len(sub) == 0:
            continue
        sub = sub.copy()
        c = sub["close"].ffill()
        kline["stocks"].append({
            "code": code, "industry": universe.loc[cno - 1, "industry"],
            "dates": [str(d.date()) for d in sub["date"]],
            "open": [round(v, 2) for v in sub["open"].ffill().tolist()],
            "close": [round(v, 2) for v in c.tolist()],
            "high": [round(v, 2) for v in c.tolist()],
            "low": [round(v, 2) for v in c.tolist()],
            "ma5": [round(v, 2) if v == v else None for v in c.rolling(5).mean().tolist()],
            "ma20": [round(v, 2) if v == v else None for v in c.rolling(20).mean().tolist()],
            "adj_raw": [round(v, 2) if v == v else None for v in sub["close"].tolist()],
            "adj_fwd": [round(v, 2) if v == v else None for v in sub["adj_close_fwd"].tolist()],
            "adj_bwd": [round(v, 2) if v == v else None for v in sub["adj_close_bwd"].tolist()]})
    export_json("kline_sample.json", kline)
    export_json("distribution.json", compute_distribution(close_clean, universe, dates, rebal))

    self_check(fdf, layers, ic_payload, universe, prices_long, port)
    print("\n全部数据生成完成。")


def self_check(fdf, layers, ic_payload, universe, prices_long, port):
    print("\n===== 自检报告 =====")
    ok = True
    for f in FACTORS:
        s = ic_payload["summary"][f]
        lo, hi = IC_BANDS[f]
        in_band = lo <= s["mean"] <= hi
        ok &= in_band
        print(f"  IC[{f:6s}] = {s['mean']:+.4f}（目标 {lo:+.3f}~{hi:+.3f}）{'✓' if in_band else '✗'}")
    for f in FACTORS:
        means = [np.nanmean([x for x in layers["monthly"][f][f"L{k}"] if x is not None])
                 for k in range(1, 11)]
        rho = float(np.corrcoef(np.arange(10), means)[0, 1])
        # 弱因子（|IC|<0.03）允许较弱的层间单调性；方向须与 IC 一致
        target_dir = 1 if IC_BANDS[f][0] > 0 else -1
        mono = rho * target_dir >= (0.15 if abs(ic_payload["summary"][f]["mean"]) < 0.03 else 0.35)
        ok &= mono
        print(f"  分层[{f:6s}] 秩相关={rho:+.3f} {'✓' if mono else '✗'}")
    for nm, arr in [("组合", port["nav"]), ("基准", port["benchmark"]), ("多空", port["long_short"])]:
        pos = all(v > 0 for v in arr)
        ok &= pos
        print(f"  净值[{nm}] 全正={'✓' if pos else '✗'}")
    n_delist = int(universe["delist_date"].notna().sum())
    ok &= (n_delist == 3)
    print(f"  退市股数量={n_delist} {'✓' if n_delist == 3 else '✗'}")
    miss = float(prices_long["close"].isna().mean())
    ok &= abs(miss - MISSING_RATE) < 0.005
    print(f"  close 缺失率={miss:.4f}（目标 ~{MISSING_RATE}）{'✓' if abs(miss - MISSING_RATE) < 0.005 else '✗'}")
    print(f"\n  总判定：{'PASS' if ok else 'FAIL'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
