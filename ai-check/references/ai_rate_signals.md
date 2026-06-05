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

## Mitigating Signals

- Citation markers such as `[4]`, `[20-22]`, `[3, 5]`.
- Concrete metrics such as `%`, FLOPs, ms, Hz, kHz, dB, AUC, F1, MB, GB.
- Named methods or models such as CNN, RNN, LSTM, GRU, Transformer, Grad-CAM, XGBoost, CQT.
- Experiment traces: datasets, comparison experiments, ablation, accuracy, computational complexity,
  evaluation protocol, failure cases.
- Explicit scope or limitations: constraints, scenarios, selected method boundaries, or authorial
  tradeoffs.

## Self-consistency Rule

Reduction should remove the risk signals that caused high scores. A medium reduction that simply
makes prose more formal, smoother, and more balanced is a failure mode because it may preserve or
increase AI-writing style.

