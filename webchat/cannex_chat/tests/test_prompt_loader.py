from webchat.cannex_chat.agent.prompt_loader import load_system_prompt


def test_prompt_loads_and_is_substantial():
    p = load_system_prompt()
    assert isinstance(p, str)
    assert len(p) > 2000


def test_prompt_has_tool_workflow_and_runtime():
    p = load_system_prompt()
    assert "检索工作流" in p
    assert "list_repo_files" in p
    assert "运行时约束" in p or "Webchat" in p


def test_prompt_has_no_phase1_cli_details():
    p = load_system_prompt()
    assert "cannex_doc.py" not in p
    assert "cannex_repo.py" not in p
    assert "附录 A" not in p


def test_prompt_loader_does_not_read_skill_md():
    """防回归：prompt_loader 必须读自己的 system_prompt.md，不依赖 SKILL.md。"""
    import inspect
    from webchat.cannex_chat.agent import prompt_loader
    src = inspect.getsource(prompt_loader)
    assert "SKILL.md" not in src
    assert "system_prompt.md" in src


def test_load_idempotent():
    assert load_system_prompt() == load_system_prompt()
