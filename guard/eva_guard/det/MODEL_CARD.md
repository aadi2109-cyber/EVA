# EVA Guard — T2 Model Card & Selection

## 1. Model Overview & Purpose
- **Component**: EVA Guard Tier 2 Sentence Classifier (`det/t2.py`).
- **Function**: Multi-head sentence-level classifier operating on CPU (onnxruntime CPUExecutionProvider, int8-quantized).
  - `main`: Probability that the sentence contains a prompt injection, jailbreak, or unauthorized directive.
  - `aux`: Probability that the sentence is a quoted, academic, or benign meta-discussion *about* prompt injection or security testing.
- **Decision Rule**: Sentences with high `main` and high `aux` are retained as benign meta-discussion and audited. Sentences with high `main` and low `aux` are flagged for surgical sanitization.

## 2. Architecture & Base Model Candidates

### Candidate A (Selected Base): `all-MiniLM-L6-v2` / `bert-base-uncased` (DistilBERT/MiniLM architecture)
- **Parameters**: ~22M to ~66M parameters.
- **Licence**: **Apache 2.0** (Open, permissive, allows commercial use and redistribution without restrictions).
- **Inference Profile**: Int8-quantized ONNX model running on CPU with 2 intra-op threads. Average latency < 5 ms per sentence, memory footprint resident < 80 MB.
- **Multi-Head Structure**:
  - Linear classification head 1 (`main`): Binary cross-entropy for injection detection.
  - Linear classification head 2 (`aux`): Binary cross-entropy for quoted/meta detection.

### Candidate B (Interim Scorer): Rule-Weighted Multi-Signal Synthesizer (`InterimTier2Scorer`)
- **Status**: Shipped in H0–H0.75 behind the exact `Tier2Scorer` interface.
- **Licence**: Internal EVA MIT/Apache-2.0.
- **Features**: Synthesizes T1 fast indicators, regex override scoring, role markers, exfiltration patterns, and quotation context without external model dependency.

## 3. Dataset Licensing & Governance
All datasets used for training and dev split evaluation adhere strictly to open-source governance:
- **Corpus Sources**:
  - Synthetic and authored enterprise injection/benign examples (Internal EVA corpus).
  - Open datasets with permissive licences (Apache 2.0 / MIT / CC-BY-4.0):
    - Lakera Gandalf baseline sets (educational/open research).
    - SPML / BIPIA datasets (filtered for permissive usage).
- **Prohibition**: **Zero tuning or training on the `test` split**. The test split is held out for unbiased final evaluation.

## 4. Hardware & Quantization Targets
- **Runtime Environment**: Developer laptop CPU execution (no GPU required).
- **Execution Provider**: `onnxruntime.InferenceSession` with `CPUExecutionProvider`.
- **Quantization**: INT8 dynamic quantization via `optimum` / ONNX runtime tools.
- **Integrity**: Hash pinned via `T2_MODEL_SHA256`. Startup verification checks model file sha256; mismatch triggers fail-closed `tier2_available=False`.
