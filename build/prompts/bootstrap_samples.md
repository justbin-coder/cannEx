你是 CANN 算子开发专家。请扫描下列算子目录，为每个独立算子生成一条 samples.yaml 条目。
注意：本仓是生产级算子实现仓（非教学样例仓），每条代表一个可参考的算子实现。

## 仓库
{repo_name}

## 算子目录列表（候选条目）
{sample_dirs}

## 每个目录可见到的文件名
{sample_files_per_dir}

## 输出要求

严格按以下 YAML schema 输出 samples: 列表，包裹在 ```yaml 中。
每条字段都必须填；不确定的填 "TBD: <你的猜测>"，便于人工 review。

`apis_used` 字段从 entry_files 的代码内容自动提取：
扫每个 entry_files 的源码，凡是匹配下方 Ascend C API 字典中任一条目的标识符，
都加入 apis_used（去重）。若代码不可获取，置为空列表 [] 并标注 "TBD: 代码未提取"。

### Ascend C API 字典（仅匹配以下名字）

{ascend_c_apis}

### 输出 schema

```yaml
samples:
  - id: <kebab-case 唯一 ID，如 flash-attention-score>
    name: <可读名，中英文均可>
    path: <相对仓根路径，如 attention/flash_attention_score>
    entry_files: [<核心 .cpp 或 .h 文件名>]
    computation_pattern: <vector | cube | vector_to_cube | cube_to_vector | fusion | TBD>
    apis_used: [<从 Ascend C API 字典自动匹配，去重>]
    complexity: <beginner | intermediate | expert | TBD>
    teaches:
      - <学习要点>
    limitations:
      - <已知局限或 "TBD">
    related_docs: []     # 关联文档章节，初稿留空，人工补
```

不要解释，只输出 YAML。
不要包含 recommendation_reason 字段。
