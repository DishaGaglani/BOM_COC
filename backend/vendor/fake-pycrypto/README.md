# Why this exists

`unstructured-inference` -> `layoutparser` has an unconditional, unpinned
dependency on `pdfplumber`. Every `pdfplumber` release from 0.7.0 onward
hard-pins an *exact* `pdfminer.six` version, none of which match the
`pdfminer.six==20240706` pin `requirements.txt` carries deliberately (newer
`pdfminer.six` releases renamed `PSSyntaxError` to `PDFSyntaxError`, which
breaks `unstructured` 0.15.13's own pdf-partitioner import — see the comment
above the `pdfminer.six` pin in `requirements.txt`).

With no compatible modern `pdfplumber` available, pip's resolver backtracks
all the way down to `pdfplumber==0.5.3`, which depends on `pycrypto` —
abandoned since ~2013, and its C extension (`_fastmath.c`) includes
`longintrepr.h`, a CPython-internal header removed in Python 3.11. It
cannot build on Python 3.11+ at all, full stop.

Neither `pdfplumber` nor `layoutparser` are imported anywhere in this
codebase directly — `pdfplumber` is only a static dependency declaration of
`layoutparser`, exercised (if at all) for encrypted-PDF handling that
`unstructured`'s own pdf pipeline doesn't route through. So: this directory
is an empty stub package satisfying pip's resolver for the literal name
"pycrypto" (no code, no C extension — nothing to build), and
`requirements.txt` separately installs `pycryptodome` (maintained, provides
the same `Crypto.*` import namespace) to cover anything that actually does
`import Crypto` at runtime.

## Install order

This stub must be installed *before* `pip install -r requirements.txt`, so
pip's resolver finds "pycrypto" already satisfied and never attempts to
build the real one:

```
pip install ./vendor/fake-pycrypto pycryptodome
pip install -r requirements.txt
```

(`backend/Dockerfile` and the "Running locally" section of the top-level
README do this in that order.)
