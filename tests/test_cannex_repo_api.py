"""
Tests for api_* functions in cannex_knowledge.retriever_repo (lib).
Imported via lib/ rather than skills/ wrapper after Task 4 refactor.
Run from project root: python3 -m pytest tests/test_cannex_repo_api.py -v
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "lib"))

from cannex_knowledge import retriever_repo as repo


def test_api_list_repos():
    result = repo.api_list()
    assert isinstance(result, list)
    assert len(result) > 0
    assert all("name" in r for r in result)


def test_api_card_returns_dict():
    result = repo.api_card("ops-transformer")
    assert isinstance(result, dict)
    # repo_card.yaml uses repo_name key
    assert "repo_name" in result or "name" in result


def test_api_symbol_returns_dict():
    result = repo.api_symbol("ops-transformer", symbol="DataCopy", kind="any")
    assert isinstance(result, dict)
    assert "matches" in result
    assert isinstance(result["matches"], list)
