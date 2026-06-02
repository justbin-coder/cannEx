"""
Tests for api_* functions in cannex_knowledge.retriever_doc (lib).
Imported via lib/ rather than skills/ wrapper after Task 5 refactor.
Run from project root: python3 -m pytest tests/test_cannex_doc_api.py -v
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "lib"))

import pytest
from cannex_knowledge import retriever_doc as doc


def test_api_list_returns_dict_list():
    result = doc.api_list()
    assert isinstance(result, list)
    assert len(result) > 0
    assert all("doc_id" in d and "doc_name" in d for d in result)
