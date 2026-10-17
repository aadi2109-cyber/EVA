import os

# Never download/load LAYA weights as a side effect of constructing Guard() in tests.
os.environ.setdefault("EVA_T3_PRELOAD", "0")
