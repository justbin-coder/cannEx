"""工具定义。

源定义 `_TOOL_SPECS` 用可读的 name/description/input_schema 风格书写，模块加载时
由 `_to_openai_tool` 编译成 litellm 要求的 OpenAI 格式（导出 `TOOLS`）。litellm 的
输入契约是 OpenAI 格式，再由它按后端翻译；详见 docs 中 BYOK/多供应商讨论。
"""

_TOOL_SPECS: list[dict] = [
    {
        "name": "lookup_code_symbol",
        "description": (
            "Locate the definition of a specific code symbol (function/class/macro). Use when "
            "user asks where something is defined or for an exact API signature."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name, e.g., 'DataCopy'"},
                "repo": {"type": "string", "description": "Repo name, default ops-transformer"},
                "kind": {
                    "type": "string",
                    "enum": ["function", "class", "macro", "any"],
                    "description": "Symbol kind filter",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "list_known_resources",
        "description": (
            "List all available knowledge sources (documents and code repos). Use at the start "
            "when user asks what you can answer, or when you need to understand the scope of "
            "available knowledge."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_document_outline",
        "description": (
            "Get the chapter outline (ToC) of a specific document. Use this BEFORE "
            "read_document_pages — first see the structure to decide which pages to read. "
            "Cheaper than full-text search when you know the user is asking about a specific topic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_name": {"type": "string",
                             "description": "Document name (substring match) or doc_id from list_known_resources"},
                "max_depth": {"type": "integer",
                              "description": "Max nesting depth, default 3"},
            },
            "required": ["doc_name"],
        },
    },
    {
        "name": "read_document_pages",
        "description": (
            "Read the original text of specified pages from a document. Use after "
            "get_document_outline tells you which pages contain the answer. "
            "Returns verbatim content for direct quotation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_name": {"type": "string", "description": "Document name or doc_id"},
                "page_range": {
                    "type": "string",
                    "description": "Page range like '5-7', '3,8', or single '12'",
                },
            },
            "required": ["doc_name", "page_range"],
        },
    },
    {
        "name": "get_repo_overview",
        "description": (
            "Get the high-level overview card of a code repo (architecture, tech stack, "
            "entry-point guidance, teaching highlights). Use this BEFORE diving into samples "
            "when user is unfamiliar with a repo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name from list_known_resources"},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "list_repo_samples",
        "description": (
            "List curated learning samples in a repo (from samples.yaml). Each sample bundles "
            "entry_files + teaching points + complexity tag. This is the HIGHEST-VALUE entry "
            "for teaching scenarios — prefer this over lookup_code_symbol when user asks how a "
            "specific operator/feature is implemented (e.g. 'FlashAttention implementation', "
            "'how is FFN done')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name"},
                "pattern": {
                    "type": "string",
                    "description": "Optional case-insensitive name/id substring filter",
                },
                "complexity": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "expert"],
                    "description": "Optional complexity filter",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "read_sample_code",
        "description": (
            "Read FULL source code of a sample's entry_files (the curated teaching files). "
            "Use after list_repo_samples to actually show the user the implementation. "
            "Set skeleton=true to first preview only top 60 lines per file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "sample_id": {"type": "string",
                              "description": "Sample id from list_repo_samples"},
                "skeleton": {
                    "type": "boolean",
                    "description": "If true, only read first 60 lines of each file (default false)",
                },
            },
            "required": ["repo", "sample_id"],
        },
    },
    {
        "name": "list_repo_files",
        "description": (
            "★★★ MUST CALL after read_sample_code if its response contains 'next_action_required' "
            "or 'sibling_archs_missing'. CANN repos have multiple hardware architecture directories "
            "(arch32 = old 910A, arch35 = new 910B/C/D, arch38 = newer). Never answer a code-explain "
            "question based on only ONE arch — list the parent dir first to discover all archXX/ peers, "
            "then read_repo_file on each. "
            "Also useful for general directory exploration: like `ls -R` with depth limit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "dir_path": {
                    "type": "string",
                    "description": "Path relative to repo root, '' for root, e.g. 'attention/common/op_kernel'",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Recursion depth, default 2",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "read_repo_file",
        "description": (
            "Read ANY source file inside a repo by relative path (the free-Read escape hatch). "
            "★★★ MUST CALL if a previous tool response contained 'next_action_required' or "
            "'sibling_archs_missing' — read each missing arch's corresponding file. "
            "Also use when lookup_code_symbol returns a file_path you want "
            "to read in depth — especially for files NOT covered by samples.yaml's entry_files. "
            "Example: after lookup_code_symbol returns file_path='op_kernel/arch35/foo.h', "
            "call read_repo_file(repo, 'op_kernel/arch35/foo.h', start_line=200, end_line=400)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "file_path": {
                    "type": "string",
                    "description": "Path relative to repo root, e.g. 'op_kernel/arch35/foo.h'",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-indexed start line, default 1",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-indexed end line (inclusive), default start_line+299",
                },
            },
            "required": ["repo", "file_path"],
        },
    },
    # ── L1 符号定位（Phase B 新增）──────────────────────────────────────────
    {
        "name": "search_code_symbol",
        "description": (
            "Search for code symbols by name using FTS5 + ranking (CodeGraph query). "
            "Use when you need to find symbols whose exact name is uncertain, or want "
            "to see the top-ranked matches for a name fragment. Returns matches with score. "
            "Prefer over lookup_code_symbol for exploratory searches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name, default ops-transformer"},
                "query": {"type": "string", "description": "Symbol name or fragment to search"},
                "kind": {
                    "type": "string",
                    "description": "Optional kind filter: function / method / class / struct / enum",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max matches to return, default 10",
                },
            },
            "required": ["repo", "query"],
        },
    },
    {
        "name": "lookup_code_node",
        "description": (
            "Get complete details for a single known symbol (query --limit 1 equivalent). "
            "Use when you already know the exact symbol name and want all its metadata "
            "(visibility, is_static, line range, qualified_name)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "symbol": {"type": "string", "description": "Exact symbol name"},
                "kind": {"type": "string", "description": "Optional kind filter"},
            },
            "required": ["repo", "symbol"],
        },
    },
    # ── L2 图关系反查（Phase B 新增）─────────────────────────────────────────
    {
        "name": "find_code_callers",
        "description": (
            "★ Find all callers of a given symbol (who calls this function/method). "
            "Use when user asks 'where is DataCopy used', 'which operators use TPipe', "
            "or 'what calls FlashAttentionScore'. Returns list with file_path + start_line "
            "for each caller. Note: may miss macro-expanded or template-specialized calls."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "symbol": {"type": "string", "description": "Symbol name to find callers of"},
                "limit": {"type": "integer", "description": "Max callers to return, default 20"},
            },
            "required": ["repo", "symbol"],
        },
    },
    {
        "name": "find_code_callees",
        "description": (
            "Find all functions/methods called by a given symbol (what does this call). "
            "Use when user asks 'what APIs does FlashAttention Process() call' or "
            "'what does this function depend on'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "symbol": {"type": "string", "description": "Symbol name to find callees of"},
                "limit": {"type": "integer", "description": "Max callees to return, default 20"},
            },
            "required": ["repo", "symbol"],
        },
    },
    {
        "name": "analyze_code_impact",
        "description": (
            "★ Analyze the change impact radius of a symbol: which files/symbols would be "
            "affected if this symbol is modified. Use for 'if I change Tiling, what breaks', "
            "'what is the blast radius of modifying FlashAttentionScoreKernelBase'. "
            "⚠️ Heavy tool — call at most ONCE per answer (depth ≥ 3 is slow)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "symbol": {"type": "string", "description": "Symbol name to analyze impact of"},
                "depth": {
                    "type": "integer",
                    "description": "Graph traversal depth, default 2 (keep low for speed)",
                },
            },
            "required": ["repo", "symbol"],
        },
    },
    # ── L4 阙割版探索（Phase B 新增）─────────────────────────────────────────
    {
        "name": "explore_code_symbols",
        "description": (
            "★ Get a task-relevant symbol list WITHOUT source code (CodeGraph context --no-code). "
            "Use for cross-cutting questions like 'what code is involved in FlashAttention pipeline', "
            "'which symbols relate to KVCache quantization'. Returns entry_points + symbols with "
            "file:line but NO source code — follow up with read_repo_file on specific entries. "
            "⚠️ Heavy tool — call at most ONCE per answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "query": {"type": "string", "description": "Task description, e.g. 'FlashAttention pipeline'"},
                "max_symbols": {
                    "type": "integer",
                    "description": "Max symbols to return, default 30",
                },
            },
            "required": ["repo", "query"],
        },
    },
    # ── 完整调用链 / 影响面（2026-05-29 新增）─────────────────────────────────
    {
        "name": "get_operator_call_chain",
        "description": (
            "★ Build an operator's COMPLETE call chain: graph traversal as the backbone, "
            "with macro/template 'seams' flagged for you to expand. Use for 'show me the full "
            "call chain of FlashAttention' or 'I want to understand this operator's execution "
            "logic before modifying it'. Returns {tree, seams, coverage}. The seams list = graph "
            "blindspots: read each seam's file_path+span with read_repo_file, expand the macro/"
            "template, then call this again on recovered symbols. ⚠️ Heavy — call at most ONCE "
            "per answer; raise read_budget only when completeness matters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "root": {"type": "string", "description": "Root symbol or operator entry name"},
                "max_depth": {"type": "integer", "description": "Graph BFS depth, default 4"},
                "read_budget": {"type": "integer",
                                "description": "Max source-body reads for seam scan, default 8 (raise to escalate completeness)"},
            },
            "required": ["repo", "root"],
        },
    },
    {
        "name": "get_change_impact_surface",
        "description": (
            "★ Analyze the change impact surface of a symbol for SECONDARY DEVELOPMENT: graph "
            "callers (precise) UNION ripgrep references (recall net for macro/template call sites "
            "the graph misses). Use for 'if I modify Tiling, what's affected'. Returns "
            "{graph_callers, ripgrep_refs, to_classify, coverage}. to_classify = ripgrep hits the "
            "graph missed — classify each (real call / comment / string / unrelated). NEVER present "
            "a low-coverage result as complete; tell the user to raise read_budget before acting. "
            "⚠️ Heavy — call at most ONCE per answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "symbol": {"type": "string"},
                "read_budget": {"type": "integer", "description": "default 8"},
            },
            "required": ["repo", "symbol"],
        },
    },
    # ── API 名称查找（2026-06-03 新增）─────────────────────────────────────────
    {
        "name": "lookup_doc_api",
        "description": (
            "★ Look up an API by name in API reference documents. Use when the user asks about "
            "a specific Ascend C API (e.g. 'how to use DataCopy', 'what are the params for "
            "MatmulApiStaticTiling'). Returns matching API entries with page ranges — follow up "
            "with read_document_pages to get the full content. PREFER this over get_document_outline "
            "when the user already knows (or you can infer) a specific API name. Falls back "
            "gracefully for non-API-reference documents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc": {"type": "string", "description": "Document name or ID (use 'operator_api_ref' for the API reference)"},
                "query": {"type": "string", "description": "API name or fragment to search, e.g. 'DataCopy', 'Matmul'"},
            },
            "required": ["doc", "query"],
        },
    },
]

def _to_openai_tool(spec: dict) -> dict:
    """把源定义(name/description/input_schema)编译成 litellm 要求的 OpenAI 格式。"""
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": spec["input_schema"],
        },
    }


TOOLS: list[dict] = [_to_openai_tool(s) for s in _TOOL_SPECS]
TOOL_NAMES = {s["name"] for s in _TOOL_SPECS}
