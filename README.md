# 量化研究入门学习资料

尚宸量化策略实习生笔试 · 交付物一：量化研究入门学习资料（GitHub Pages 网页版）
笔试题目背景：[【尙宸】量化策略实习生笔试题目.pdf]（不随仓库分发）

## 这是什么

面向"具备金融基础与 Python 数据分析能力、但不熟悉量化多因子研究流程"的新实习生，
以**完整研究流程**为主线的入门学习资料：

```
数据获取与清洗 → 因子构建 → 因子检验 → 因子合成 → 组合构建 → 回测与评估 → 绩效归因
```

每章 = 概念讲解 + 交互图表（ECharts）+ 可运行 Notebook + 常见误区 + 思考题。
全部数据为模拟数据（固定种子，可完整复现），网页图表数据均可从 CSV 一步步重算。

## 在线地址

https://wenbin778899.github.io/quant-research-learning/

## 目录导览

| 路径 | 内容 |
|---|---|
| `index.html` | 学习路径主页（流程全景 + 章节导航 + 阅读路线） |
| `chapters/ch1-data.html` ~ `ch7-attribution.html` | 七个核心章节 |
| `appendix.html` | 术语表 / 数据字典 / Notebook 索引 / 复现说明 |
| `process.html` | 研究过程与提问（交付物二网页版） |
| `docs/QUESTIONS.md` | 交付物二：对 AI 的所有提问记录 |
| `docs/DESIGN.md` | 详细设计方案 |
| `data/csv/` | 全量模拟数据（prices / factors / dividends / stocks_basic） |
| `data/*.json` | 网页图表聚合数据 |
| `notebooks/` | 7 本可运行教学 Notebook（末 cell 自动校验与网页数据一致） |
| `scripts/generate_data.py` | 数据生成脚本（唯一数据源） |
| `scripts/make_notebooks.py` | Notebook 生成脚本 |

## 快速开始

```bash
# 1. 依赖
pip install -r scripts/requirements.txt

# 2. 生成全部数据（含自检报告）
python scripts/generate_data.py

# 3. 本地预览
python -m http.server 8000
# 打开 http://localhost:8000/

# 4. （可选）执行 notebook 一致性校验
python scripts/make_notebooks.py        # 重新生成 notebook
jupyter nbconvert --to notebook --execute notebooks/*.ipynb   # 或逐本执行
```

## 模拟数据设计（教学点）

- **200 只股票 × 8 行业**，2020-2024 共 60 个月度调仓期
- **3 只退市股**（退市前连续大跌）→ 幸存者偏差教学点
- **30% 股票季度分红 + 送股** → 复权教学点
- **随机缺失 + 停牌** → 数据清洗教学点
- **8 个因子分级预测力**：强因子（EP/MOM60/ROE/GROW，月 IC≈0.06）、中（REV5≈0.05）、弱（SIZE/VOL20/TURN，|IC|≤0.02，SIZE 负向呼应小市值效应）
- alpha 系数经**自动校准**迭代收敛，IC 落入贴近真实研究的区间

## 一致性保证

生成脚本内部的分析一律基于「prices.csv 注入缺失 → ffill → 剔除退市后区间」的清洗序列；
Notebook 从 CSV 读入后执行**相同的清洗**再重算，末 cell 用 `np.allclose` 对照网页 JSON——
网页上每一张图都可以从原始 CSV 一步步重算出来。

## 技术栈

纯静态站点：HTML + CSS（明暗双主题）+ ECharts 5（本地化 + CDN 兜底）+ 预计算 JSON 数据。
GitHub Pages 托管（main 分支根目录），零构建。

## 笔试交付物清单

1. 量化研究入门学习资料 = 本网站（线上可访问）+ 7 本 Notebook + 数据生成脚本与全量数据
2. 对 AI 的所有提问 = `docs/QUESTIONS.md` + 网页「研究过程与提问」页（同源数据）

## 免责声明

全部行情/因子/收益数据为教学用途的模拟数据，不构成任何投资建议。
