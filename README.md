# linchuan

个人代码与笔记仓库。目前包含一套考证复习用的刷题与笔记辅助工具。

## 使用

```bash
git clone https://github.com/1779357400/linchuan.git
cd linchuan
```

## 目录结构

```
.
├── scripts/
│   └── study.py      # 刷题与笔记辅助工具
├── data/             # 刷题记录（JSONL）
├── notes/            # Markdown 笔记与索引
├── README.md
├── LICENSE
└── .gitignore
```

## 刷题与笔记工具

无第三方依赖，Python 3.11+ 直接运行。

### 记录错题

```bash
python scripts/study.py add "甲将房屋卖给乙并交付但未过户，乙能否取得所有权？" \
  -s 民法 -t 物权 --mine 能 --answer 不能 \
  --reason "不动产物权变动以登记为生效要件" --ref "民法典第209条"
```

答对的题加 `--correct` 标记，不进错题复习队列。

### 复习

```bash
python scripts/study.py review            # 查看今日到期的错题
python scripts/study.py review --pass bc50   # 已掌握，间隔拉长
python scripts/study.py review --fail bc50   # 仍不熟，间隔重置
```

采用简化版 SM-2 间隔重复：首次通过隔 1 天，第二次 3 天，之后按难度系数递增；未通过则重置为 1 天并降低难度系数。

### 统计与导出

```bash
python scripts/study.py stats              # 总体正确率与分科统计
python scripts/study.py stats --days 7     # 只看最近一周
python scripts/study.py list --wrong       # 列出全部错题
python scripts/study.py export             # 导出为 notes/错题本.md
```

### 笔记

```bash
python scripts/study.py note "善意取得的构成要件" --tags 民法,物权
python scripts/study.py index              # 重建 notes/INDEX.md
```

`note` 会在 `notes/` 下生成带 front matter 的 Markdown 模板；`index` 只收录带 front matter 的笔记，不会把索引本身和导出的错题本算进去。

### 数据说明

记录以 JSONL 追加写入 `data/attempts.jsonl`，一行一条，纯文本便于 diff 与人工修改。该文件默认纳入版本管理以实现跨设备同步；若希望记录只留在本地，在 `.gitignore` 中加入 `data/attempts.jsonl` 即可。

## 环境

- Python 3.11+（仅用标准库）
- 建议使用虚拟环境：

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
```

## 约定

- 主分支：`main`
- 提交信息使用约定式前缀：`feat:` / `fix:` / `docs:` / `chore:`
- 代码风格遵循 `.editorconfig`：Python 缩进 4 空格，其余 2 空格；统一 LF 换行

## 许可

MIT，详见 [LICENSE](LICENSE)。
