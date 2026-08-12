# test_e2e.py is a live-server E2E agent (run as: python tests/test_e2e.py),
# not a pytest suite; its test_* functions take runtime args, not fixtures,
# so collecting it produces 5 fixture errors. Excluded here rather than via
# addopts --ignore because collect_ignore resolves relative to this file,
# not the invocation directory.
collect_ignore = ["test_e2e.py"]
