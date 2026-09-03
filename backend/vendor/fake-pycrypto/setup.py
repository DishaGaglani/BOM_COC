from setuptools import setup

# Empty stub satisfying pip's dependency resolver for "pycrypto" — see
# backend/vendor/fake-pycrypto/README.md for why this exists. No code, no C
# extension, nothing to build; the real Crypto.* import surface at runtime
# is provided by pycryptodome instead (see requirements.txt).
setup(name="pycrypto", version="2.6.1", packages=[])
