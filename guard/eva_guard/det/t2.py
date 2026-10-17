"""
T2 — Tier 2 Sentence Classifier.
Defines the Tier2Scorer interface, the InterimTier2Scorer (H0-H0.75 deliverable),
and the OnnxTier2Scorer (for quantized multi-head ONNX models).
Multi-head:
- main: injection probability [0.0, 1.0]
- aux: quoted/meta discussion probability [0.0, 1.0]
Decision rule: high main + high aux -> benign meta discussion, keep and audit.
"""
import os
import re
import hashlib
import logging
from typing import NamedTuple
from eva_guard.det.t1 import scan_t1
from eva_guard.det.config import DetConfig

logger = logging.getLogger(__name__)


# A "bare data" fragment carries no instruction: a lone address, URL, number/date, or just a YAML key.
# The learned model over-fires on such fragments (it treats `com`/`org`/`@` as attack tokens), which strips
# participant lists and similar structured data from tool output. T1 rules still apply to them.
_ADDR = r"<?[\w.+-]+@[\w-]+(?:\.[\w-]+)+>?"
_LITERAL = r"(?:true|false|null|none|yes|no|~|r|rw|w|read|write|\d+)"          # flags / permission codes
_VALUE = rf"(?:{_ADDR}(?:\s*[,;]\s*{_ADDR})*|https?://[^\s?#]+/?|\d[\d\-:/. TZ+]*|{_LITERAL}(?![\w]))"
_BARE_DATA = re.compile(
    rf"""^\s*(?:-\s*)?                        # optional YAML list dash
        (?:(?:{_ADDR}|["']?[A-Za-z_][\w ]{{0,30}}["']?):\s*)?   # optional `key:` (a plain key or an address)
        ["']?(?:{_VALUE})?["']?\s*,?\s*$""", re.VERBOSE)


def is_bare_data(sentence: str) -> bool:
    """True for fragments such as `- a@b.com`, `email: a@b.com`, `participants:`, `date: 2024-05-26`."""
    s = sentence.strip()
    return bool(s) and len(s) <= 200 and _BARE_DATA.match(s) is not None


class Score(NamedTuple):
    main: float
    aux: float
    meta_injection_discussed: bool = False

class Tier2Scorer:
    """Base interface for Tier 2 scoring."""
    def score(self, sentences: list[str]) -> list[Score]:
        raise NotImplementedError

    @property
    def is_available(self) -> bool:
        return True

    @property
    def model_hash(self) -> str | None:
        return None

# Patterns indicating discussion/quoting of injection rather than an actual attack
_META_DISCUSSION_PATTERNS = [
    re.compile(r"""(?i)(?:example|payload|test|string|phrase|attack)\s*(?:such\s+as|like|is|:)\s*["'`]"""),
    re.compile(r"""(?i)["'`]\s*(?:ignore\s+previous|system\s*:|forward\s+all)\s*["'`]"""),
    re.compile(r"""(?i)\b(?:research(?:ers)?|paper|study|demonstrated|benchmarking|evaluating|defending\s+against)\b"""),
    re.compile(r"""(?i)\b(?:prompt\s+injections?|jailbreaks?|indirect\s+injection)\b"""),
    re.compile(r"""(?i)\b(?:common|known|typical|classic)\s+(?:attack|injection|jailbreak)s?\b|\bwhich\s+is\s+why\s+we\s+(?:sanitis|sanitiz|filter|block)"""),
    re.compile(r"""(?i)\b(?:we\s+found\s+that|users\s+might\s+input|adversary\s+can)\b"""),
]

class InterimTier2Scorer(Tier2Scorer):
    """
    Interim Tier-2 scorer available from Hour 0.
    Combines fast rules and heuristic meta-analysis behind the Tier2Scorer interface
    to enable full end-to-end testing while the ONNX model is finalized.
    """
    def __init__(self, config: DetConfig | None = None) -> None:
        self.config = config or DetConfig()
        self._hash = "interim-rules-v1"

    @property
    def is_available(self) -> bool:
        return True

    @property
    def model_hash(self) -> str | None:
        return self._hash

    def score(self, sentences: list[str]) -> list[Score]:
        results: list[Score] = []
        for s in sentences:
            if not s or not s.strip():
                results.append(Score(main=0.0, aux=0.0, meta_injection_discussed=False))
                continue

            t1_res = scan_t1(s)
            main_score = t1_res.score

            # Check for meta-discussion patterns
            aux_score = 0.0
            meta_matches = sum(1 for p in _META_DISCUSSION_PATTERNS if p.search(s))
            if meta_matches > 0:
                aux_score = min(0.95, 0.4 + (meta_matches * 0.25))

            # If high main and high aux, flag meta injection discussion
            is_meta = (main_score >= 0.70 and aux_score >= 0.65)
            results.append(Score(main=main_score, aux=aux_score, meta_injection_discussed=is_meta))

        return results

class OnnxTier2Scorer(Tier2Scorer):
    """
    Multi-head ONNX sentence classifier (main: injection, aux: quoted/meta) on CPU.
    Verifies the main model's SHA-256 against the pin at load; any failure -> unavailable
    (the pipeline then applies its configured failure mode).
    The main score is floored by the T1 rule score so rules are never weakened by the model.
    """
    BATCH_SIZE = 64

    def __init__(self, config: DetConfig) -> None:
        self.config = config
        self._main = None
        self._aux = None
        self._hash: str | None = None
        self._available = False
        self.unavailable_reason: str | None = None
        self._load_model()

    @staticmethod
    def _sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _session(self, path: str):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.config.intra_op_threads
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        return ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])

    def _load_model(self) -> None:
        cfg = self.config
        if not (os.path.exists(cfg.t2_model_path) and os.path.exists(cfg.t2_aux_model_path)):
            self.unavailable_reason = "model file(s) not found"
            logger.warning("T2 unavailable: %s (%s)", self.unavailable_reason, cfg.t2_model_path)
            return
        try:
            self._hash = self._sha256(cfg.t2_model_path)
            if cfg.t2_model_sha256 and cfg.t2_model_sha256 != self._hash:
                self.unavailable_reason = "model SHA-256 does not match the pin"
                logger.warning("T2 unavailable: %s", self.unavailable_reason)
                return  # hash mismatch -> unavailable (fail closed)
            self._main = self._session(cfg.t2_model_path)
            self._aux = self._session(cfg.t2_aux_model_path)
            self._available = True
        except Exception as exc:
            self._main = self._aux = None
            self._available = False
            self.unavailable_reason = f"{type(exc).__name__}: {exc}"
            logger.warning("T2 unavailable: %s", self.unavailable_reason)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def model_hash(self) -> str | None:
        return self._hash

    @staticmethod
    def _positive_probs(session, batch) -> list[float]:
        out = session.run(None, {session.get_inputs()[0].name: batch})
        return [float(row[1]) for row in out[1]]

    def score(self, sentences: list[str]) -> list[Score]:
        if not self._available:
            raise RuntimeError("Tier 2 ONNX model is not available")
        if not sentences:
            return []
        import numpy as np
        bare = [is_bare_data(s) for s in sentences]
        idx = [i for i, b in enumerate(bare) if not b]          # only non-bare fragments go to the model
        todo = [sentences[i] for i in idx]
        main_m: list[float] = []
        aux_m: list[float] = []
        for i in range(0, len(todo), self.BATCH_SIZE):  # bound peak memory on huge fields
            batch = np.array([[s.lower()] for s in todo[i:i + self.BATCH_SIZE]], dtype=object)
            main_m += self._positive_probs(self._main, batch)
            aux_m += self._positive_probs(self._aux, batch)
        main = [0.0] * len(sentences)
        aux = [0.0] * len(sentences)
        for j, i in enumerate(idx):
            main[i], aux[i] = main_m[j], aux_m[j]
        results: list[Score] = []
        for s, m, a, b in zip(sentences, main, aux, bare):
            if not s.strip():
                results.append(Score(main=0.0, aux=0.0))
                continue
            m = max(m, scan_t1(s).score)                        # bare fragments: rules only (m starts at 0)
            hits = sum(1 for p in _META_DISCUSSION_PATTERNS if p.search(s))
            if hits:
                a = max(a, min(0.95, 0.4 + hits * 0.25))  # rule-based meta signal floors the aux head
            results.append(Score(main=m, aux=a, meta_injection_discussed=(m >= self.config.t2_meta_min_main and a >= self.config.t2_meta_min_aux)))
        return results

def create_t2_scorer(config: DetConfig, use_interim: bool = False) -> Tier2Scorer:
    """Factory for Tier 2 scorer."""
    if use_interim or not os.path.exists(config.t2_model_path):
        return InterimTier2Scorer(config)
    return OnnxTier2Scorer(config)
