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

## 常见问题与注意事项

### Python 版本要求

本项目要求 **Python >= 3.11**。如果当前环境 Python 版本过低（如 3.6/3.9），`pip install -e .` 会失败。

**解决方案：** 使用 conda 安装 Python 3.11：

```bash
conda create -n dragon python=3.11 -y
conda activate dragon
pip install -e .
```

### `pip install -e .` 报错：missing the 'build_editable' hook

如果执行 `pip install -e .` 时出现以下错误：

```
ERROR: ... has a 'pyproject.toml' and its build backend is missing the 'build_editable' hook.
```

说明 `pyproject.toml` 中缺少 `[build-system]` 配置。请确保文件中包含以下内容（已修复）：

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"
```

### macOS Homebrew SSL 证书问题

在较旧的 macOS（如 macOS 12）上，Homebrew 可能因 SSL 证书问题无法下载 Python。

**解决方案：** 优先使用 conda 安装 Python 3.11，而非 Homebrew。

### API Key 配置

运行 `dragon` 前必须配置 DeepSeek API Key，否则程序会报错退出。

配置方式（按优先级）：

1. **环境变量**：
   ```bash
   DEEPSEEK_API_KEY=sk-xxx dragon
   ```

2. **当前目录配置文件**：创建 `config.toml`
   ```toml
   api_key = "sk-xxx"
   ```

3. **全局配置文件**：`~/.dragon/config.toml`
   ```toml
   api_key = "sk-xxx"
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
