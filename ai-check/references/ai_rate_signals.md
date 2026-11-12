# AI-rate Signal Vocabulary

Use these signals to keep detection and reduction self-consistent. They are evidence for the
assistant, not an automatic probability.

## Risk Signals

- Template phrase: `首先...其次...最后`, `综上所述`, `由此可见`, `值得注意的是`, `不可否认`,
  `毋庸置疑`, `显而易见`, `众所周知`, `不言而喻`.
- Contribution-list style: `主要研究工作如下`, `本文提出...实验结果表明`, or several claims with
  the same sentence skeleton.
- Uniform rhythm: many sentences with similar length and a polished, frictionless cadence.
- Dense connectors: frequent `因此`, `然而`, `同时`, `此外`, `另外`, `进一步`, `具体而言`, `一方面`,
  `另一方面`.
- Generic value claims: broad claims about important significance, broad prospects, theoretical and
  practical value, reliable/intelligent systems, or a series of challenges without local detail.
- Generic closure: paragraph ends with broad praise or a one-size-fits-all conclusion.
- Missing boundary: no limitation, condition, method choice, data source, or local research context.
- Trend openers and closers: `随着…的快速发展`, `在…背景下`, `总而言之`, `总的来说`, `值得一提的是`, `需要指出的是`.
- Enumerations: `一是…二是…三是`, `不仅…更…`.
- Buzzwords: `赋能`, `助力`, `深度融合`, `全方位`, `多维度`, `新范式`, `至关重要`, `发挥着重要作用`,
  `提供了有力支撑`, `奠定了坚实基础`, `日益凸显`.
- Stacked dashes: two or more `——` (or English em dashes `—`) used as clause glue in one passage.
- Reframing contrast: `不是…而是…`, `并非…而是…` used to dramatise an ordinary point.
- Role and closer formulas: `扮演着…角色`, `为…提供了新的思路/视角/参考`, `具有一定的参考价值`,
  `从…到…再到…` staged ranges.
- Policy-report jargon in a paper: `抓手`, `提质增效`, `降本增效`, `全链条`, `多措并举`.
- Repeated sentence openers (句首重复): three or more sentences in one passage (and at least 40% of
  them) start with the same word, e.g. `本文…本文…本文…`.
- Unquantified effect claims (效果表述缺少数据): `显著提升`, `有效降低`, `大幅改善` in a sentence
  that contains no number.

## English Risk Signals

- Template phrases: `In conclusion`, `In summary`, `It is worth noting that`, `It is important to note`,
  `not only … but also`, `Firstly … Secondly … Finally`, `In today's rapidly evolving …`.
- Dense connectors: `moreover`, `furthermore`, `additionally`, `however`, `therefore`, `consequently`,
  `notably`, `overall`.
- LLM-flavoured vocabulary: `delve`, `tapestry`, `pivotal`, `underscore`, `showcase`, `intricate`,
  `multifaceted`, `realm`, `seamless`, `cutting-edge`, `paving the way`, `shed light on`,
  `plays a crucial role`, `significant implications`.
- Contribution lists: `Our main contributions are …`.
- Reframing: `It's not just X, it's Y`; scene-setting: `In the realm/landscape of …`;
  `serves as a testament/cornerstone`; `highlights the importance of`.
- More LLM-flavoured vocabulary: `foster`, `leverage`, `holistic`, `nuanced`, `meticulous`,
  `interplay`, `a myriad of`, `plethora`, `bolster`, `elucidate`, `unveil`, `harness`.
- Unquantified effect claims: `significantly improves`, `substantially reduces` with no number in the
  sentence.

Each English signal is weak evidence on its own; many of these words are legitimate in technical prose.

## Mitigating Signals

- Citation markers such as `[4]`, `[20-22]`, `[3, 5]`.
- Citation markers in author-year form such as `(Smith et al., 2024)`, LaTeX `\cite{key}` /
  `\citep{..}` and Pandoc `[@key]`.
- Concrete metrics such as `%`, FLOPs, ms, Hz, kHz, dB, AUC, F1, MB, GB, mAP, mIoU, BLEU, PSNR, SSIM.
- Statistics such as `p < 0.05`, `±`, `95% CI`, `n = 30`, 标准差, 置信区间.
- Named methods or models such as CNN, LSTM, Transformer, ResNet-50, YOLOv8, Grad-CAM, XGBoost, CQT, and
  any CamelCase/acronym model name; two or more distinct names in one passage add `领域方法细节`.
- Experiment traces: datasets, comparison experiments, ablation, accuracy, computational complexity,
  evaluation protocol, failure cases.
- Explicit scope or limitations: constraints, scenarios, selected method boundaries, or authorial
  tradeoffs.

## Self-consistency Rule

Reduction should remove the risk signals that caused high scores. A medium reduction that simply
makes prose more formal, smoother, and more balanced is a failure mode because it may preserve or
increase AI-writing style.


## Document-level Checks

- Internal repetition (前后重复表述): near-identical sentences of similar length that appear twice in
  the same paper (shingle containment >= 0.8). Common causes are the abstract copied into the
  conclusion and chapter summaries repeating the introduction. This compares the paper with itself
  only; it is not a similarity/plagiarism check against other sources.
- Section breakdown: suspicious characters and weighted rate per section, ranked by contribution to
  the overall rate, so the user knows which chapter to revise first.
- Before/after comparison (`compare`): signal counts, uniform-rhythm passages, citation marks and
  length before and after a revision. A revision that removes template phrases but adds uniform
  rhythm or drops citations is flagged.
