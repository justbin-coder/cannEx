import os
from pathlib import Path


def test_root_falls_back_to_repo_root_when_env_unset(monkeypatch):
    monkeypatch.delenv("CANNEX_ROOT", raising=False)
    import importlib
    from cannex_knowledge import paths
    importlib.reload(paths)
    # paths.py 在 lib/cannex_knowledge/ 下，parents[2] = CannEx 根
    assert paths.CANNEX_ROOT.name == "CannEx"
    assert paths.WORKSPACE == paths.CANNEX_ROOT / "workspace"
    assert paths.META_FILE == paths.WORKSPACE / "_meta.json"
    assert paths.REPOS_DIR == paths.WORKSPACE / "repos"


def test_root_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CANNEX_ROOT", str(tmp_path))
    import importlib
    from cannex_knowledge import paths
    importlib.reload(paths)
    assert paths.CANNEX_ROOT == tmp_path
    assert paths.WORKSPACE == tmp_path / "workspace"
