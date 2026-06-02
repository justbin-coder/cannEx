from cannex_knowledge import seam


def test_detects_macro_call():
    src = "INVOKE_FA_GENERAL_OP_IMPL(op, tiling);\nREGIST_MATMUL_OBJ(&pipe, ws);"
    out = seam.detect_seams(src)
    tokens = {(s["kind"], s["token"]) for s in out}
    assert ("macro", "INVOKE_FA_GENERAL_OP_IMPL") in tokens
    assert ("macro", "REGIST_MATMUL_OBJ") in tokens


def test_detects_template_call():
    src = "FlashAttentionScoreKernelTrain<CubeBlockType, VecBlockType>::Process();"
    out = seam.detect_seams(src)
    assert any(s["kind"] == "template" for s in out)


def test_detects_std_conditional():
    src = "using T = typename std::conditional<g_coreType == AIC, A, B>::type;"
    out = seam.detect_seams(src)
    assert any(s["token"] == "std::conditional" for s in out)


def test_excludes_false_positive_allcaps():
    src = "if (ptr == NULL) return TRUE;"
    assert seam.detect_seams(src) == []


def test_dedups_repeated_macro():
    src = "FOO_BAR(a);\nFOO_BAR(b);\nFOO_BAR(c);"
    out = [s for s in seam.detect_seams(src) if s["kind"] == "macro"]
    assert len(out) == 1


def test_empty_source():
    assert seam.detect_seams("") == []
