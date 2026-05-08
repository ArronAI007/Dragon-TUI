# Dragon TUI

基于 Python 和 Textual 构建的 Dragon TUI。

## 启动方式

### 1. 开发环境直接运行

```bash
source .venv/bin/activate
python app.py
python app.py --config ./config.toml
```

### 2. 安装为命令行工具

```bash
pip install -e .
dragon
dragon --config ./config.toml
```

> 也兼容旧命令 `dragon-tui`。

### 3. 打包/分发安装

```bash
# 构建后使用 install.sh 安装
./install.sh               # 安装到 ~/.local/bin
./install.sh /usr/local    # 安装到系统目录（需 sudo）
```

## 必要条件

必须配置 API Key，程序按以下优先级读取：

1. 环境变量：`DEEPSEEK_API_KEY=sk-xxx dragon`
2. 当前目录的 `config.toml`
3. `~/.dragon/config.toml`

未配置时程序会退出并提示错误。

## 项目结构

| 目录/文件 | 作用 |
|-----------|------|
| `app.py` | 主入口，Textual App 定义 |
| `api/` | DeepSeek API client |
| `mcp/` | MCP (Model Context Protocol) 支持 |
| `session/` | 会话管理与会话存储 |
| `tools/` | 内置工具注册表 |
| `ui/` | Textual 界面组件（输入框、消息、主题等） |
| `config.py` | 配置加载逻辑 |
| `pyproject.toml` | 项目依赖与脚本入口 |

## 依赖安装

```bash
source .venv/bin/activate
pip install -e .
```

核心依赖：`textual`, `httpx`, `pydantic`, `tiktoken`。安装后即可使用 `dragon` 命令启动。
