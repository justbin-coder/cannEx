你是 CANN 技术专家，请基于下列素材生成代码仓的"定位卡片"。

## 仓库信息
- 仓库名：{repo_name}
- URL：{repo_url}
- 默认分支/版本：{ref}

## 素材
### README 前 4000 字符
{readme_excerpt}

### 一级目录列表
{top_dirs}

## 输出要求
严格按以下 YAML schema 输出（用 ```yaml 包裹），所有字段必须填，不确定的写 "TBD: <你的猜测>"。

```yaml
repo_name: {repo_name}
repo_url: {repo_url}
audience: []         # 从 [A, B, F] 中选 1-3 个；A=算子开发者 B=应用开发者 F=代码仓贡献者
category: ""
tagline: ""          # 一句话定位（≤30 字）
scenarios:           # 3-5 条
  - ""
not_for:             # 2-3 条
  - ""
key_paths:           # 3-6 条
  - path: ""
    desc: ""
contribution:
  guide_path: ""
  pr_template: ""
maintained_by: cannex_team
last_reviewed: "{today}"
```

不要解释，只输出 YAML。
