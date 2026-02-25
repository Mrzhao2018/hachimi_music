# Hachimi Music 🎵

**AI 驱动的音乐生成系统** —— 从自然语言描述到完整音频，一句话作曲。

基于大语言模型（LLM）生成 ABC 记谱法乐谱，经 MIDI 转换、FluidSynth 音频合成、音效后处理，最终输出高质量 MP3/WAV 音频文件。提供 Web UI 进行可视化创作、编辑与试听。

## ✨ 核心特性

- **自然语言作曲** —— 用中文/英文描述想要的音乐，AI 自动生成完整多声部乐谱
- **AI 参数推荐** —— 输入描述后一键推荐风格、调性、速度、乐器编配
- **10 种音乐风格** —— Classical / Pop / Jazz / Rock / Electronic / Folk / Blues / Latin / Ambient / Cinematic
- **多声部支持** —— 最多 16 个独立声部，覆盖全部 128 种 General MIDI 乐器 + 中文乐器名
- **Studio 编辑工作室** —— 五层渐进式编辑：一键预设 → 速度调节 → 乐器轨道 → 自由文本 AI 修改 → 高级 ABC 源码编辑
- **AI 听音诊断** —— 多模态分析生成的音频，给出评分与具体改进建议，支持一键应用
- **乐谱可视化** —— abcjs 实时渲染五线谱，播放时光标同步跟随
- **音频后处理** —— 混响、压缩、归一化、淡入淡出，专业级音质输出
- **断点续作** —— 管线支持从任意阶段恢复，生成失败不丢失进度
- **项目管理** —— 完整的项目 CRUD，历史记录持久化保存
- **零配置启动** —— 内置 FluidSynth 自动安装、SoundFont 下载、四级合成降级策略

## 🛠 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **后端框架** | FastAPI + Uvicorn | RESTful API 服务，异步任务执行 |
| **LLM 集成** | OpenAI 兼容 API (httpx) | 支持 Gemini / GPT / 任意兼容端点 |
| **记谱解析** | music21 | ABC 记谱法解析与 MIDI 生成 |
| **MIDI 处理** | pretty-midi, mido | MIDI 文件读写与时长分析 |
| **音频合成** | FluidSynth (midi2audio) | SoundFont 采样合成，MIDI → WAV |
| **音频后处理** | pedalboard (Spotify) + pydub | 混响/压缩/归一化 + 格式转换 |
| **前端** | 原生 HTML/CSS/JS + abcjs | 零依赖构建，五线谱实时渲染 |
| **数据验证** | Pydantic v2 | 请求/响应模型，配置管理 |
| **配置** | YAML + pydantic-settings | 分层配置，运行时热更新 |
| **测试** | pytest + pytest-asyncio | 39 个测试用例，覆盖全部模块 |

## 📁 项目结构

```
hachimi_music/
├── hachimi/                    # 后端核心包
│   ├── api/
│   │   └── routes.py           # FastAPI 路由（22 个端点）
│   ├── core/
│   │   ├── schemas.py          # Pydantic 数据模型
│   │   ├── pipeline.py         # 四阶段生成管线
│   │   ├── config.py           # YAML 配置加载
│   │   └── project.py          # 项目持久化管理
│   ├── generation/
│   │   ├── llm_generator.py    # LLM 作曲/改编/分析
│   │   └── prompts/            # 8 个 Prompt 模板
│   ├── conversion/
│   │   ├── abc_to_midi.py      # ABC → MIDI 转换
│   │   └── instrument_mapper.py # GM 乐器映射（128 种）
│   └── synthesis/
│       ├── fluidsynth_renderer.py  # 音频合成（四级降级）
│       └── postprocess.py      # 音效后处理链
├── frontend/                   # Web 前端
│   ├── index.html              # 单页应用主页
│   ├── app.js                  # 交互逻辑（1200+ 行）
│   └── style.css               # 深色主题样式
├── config/
│   └── settings.yaml           # 运行配置
├── scripts/
│   ├── generate.py             # CLI 命令行入口
│   ├── download_soundfonts.py  # SoundFont 下载器
│   └── install_fluidsynth.py   # FluidSynth 安装器
├── tests/                      # 测试套件（6 个模块）
├── soundfonts/                 # SoundFont 音色库（.gitignore）
├── projects/                   # 项目数据持久化（.gitignore）
├── output/                     # 生成输出文件（.gitignore）
└── pyproject.toml              # 项目元数据与依赖
```

## 🚀 快速开始

### 环境要求

- Python ≥ 3.10
- FluidSynth ≥ 2.0（可通过 Web UI 自动安装）
- 一个支持 OpenAI 兼容 API 的 LLM 服务（Gemini / GPT / DeepSeek 等）

### 1. 安装

```bash
# 克隆项目
git clone https://github.com/your-username/hachimi-music.git
cd hachimi-music

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"
```

### 2. 配置 API Key

在项目根目录创建 `.env` 文件：

```env
OPENAI_API_KEY=your-api-key-here
```

或在 Web UI 的设置面板中配置。

### 3. 配置 LLM 端点

编辑 `config/settings.yaml`：

```yaml
ai:
  base_url: https://generativelanguage.googleapis.com/v1beta/openai/  # Gemini
  # base_url: https://api.openai.com/v1  # OpenAI
  # base_url: https://api.deepseek.com/v1  # DeepSeek
  model: gemini-3-flash-preview
  temperature: 0.8
```

### 4. 启动服务

```bash
# 启动 Web 服务器（默认端口 8000）
uvicorn hachimi.api.routes:app --host 0.0.0.0 --port 8000

# 或指定前端端口分离开发
uvicorn hachimi.api.routes:app --port 8001
```

打开浏览器访问 `http://localhost:8000` 即可开始创作。

### 5. 环境设置（首次使用）

首次启动后，点击侧栏底部的 **环境设置**：

1. **安装 FluidSynth** —— 点击安装按钮，自动下载 FluidSynth v2.4.0（Windows）
2. **下载 SoundFont** —— 选择 MuseScore_General（208MB，推荐）或 FluidR3_GM（148MB）

> 💡 如果不安装 FluidSynth，系统会自动降级使用 pretty_midi 内置合成器（音质较基础）。

### CLI 命令行使用

```bash
# 直接生成音乐
hachimi "一段轻快的爵士钢琴曲" --style jazz --tempo 140

# 完整参数
hachimi "宏大的交响乐" \
  --style cinematic \
  --key "D minor" \
  --time-signature 3/4 \
  --tempo 80 \
  --measures 32 \
  --instruments violin cello flute "french horn" \
  --format wav
```

## 🏗 系统架构

### 生成管线（Pipeline）

```
用户输入（自然语言）
    │
    ▼
┌─────────────────────────────────────────────┐
│  Stage 1: Generating（LLM 生成）             │
│  ├─ Step 1: 生成元数据 JSON                  │
│  │  （标题、作曲家、乐器分配、描述）           │
│  ├─ Step 2: 生成 ABC 记谱法纯文本             │
│  │  （基于元数据，多声部完整乐谱）             │
│  └─ 内置重试 + ABC 结构验证                   │
├─────────────────────────────────────────────┤
│  Stage 2: Converting（谱面转换）              │
│  ├─ music21 解析 ABC → Score 对象             │
│  ├─ GM 乐器映射 + MIDI 通道分配               │
│  ├─ 自动修复小节容器 + 重复记号处理            │
│  └─ 输出标准 MIDI 文件                        │
├─────────────────────────────────────────────┤
│  Stage 3: Rendering（音频合成）               │
│  ├─ 优先: midi2audio (FluidSynth Python)     │
│  ├─ 降级1: FluidSynth CLI                    │
│  ├─ 降级2: pyfluidsynth 直接事件播放          │
│  └─ 降级3: pretty_midi 内置波形合成           │
├─────────────────────────────────────────────┤
│  Stage 4: Postprocessing（后处理）            │
│  ├─ Reverb 混响（可配置 room_size）           │
│  ├─ Compressor 轻压缩                        │
│  ├─ Normalize 峰值归一化至 -1dB              │
│  ├─ Trim 裁剪尾部静音                        │
│  └─ 格式转换 MP3 (192kbps) + 淡入淡出        │
└─────────────────────────────────────────────┘
    │
    ▼
  音频文件 (MP3/WAV) + 乐谱 + MIDI
```

每个阶段完成后自动保存检查点（`PipelineCheckpoint`），支持通过 `resume_from` 参数从任意阶段恢复。

### LLM 两步生成策略

传统方法让 LLM 一次生成完整 JSON（含 ABC 记谱），容易因 JSON 格式约束导致 ABC 内容被截断或转义错误。本项目采用**两步分离策略**：

1. **第一步 — 元数据 JSON**：生成标题、乐器分配等结构化数据（短小 JSON，不易出错）
2. **第二步 — ABC 纯文本**：基于元数据，专注生成 ABC 记谱内容（纯文本，无格式限制）

配合 `_quick_validate_abc()` 验证器检查 `X:`/`K:` 头部、截断检测、声部数量匹配。

### 四级合成降级

FluidSynth 环境可能存在多种安装状态，系统自动选择最佳可用方案：

| 优先级 | 方法 | 要求 | 音质 |
|--------|------|------|------|
| 1 | midi2audio | FluidSynth + Python 绑定 | ⭐⭐⭐⭐⭐ |
| 2 | FluidSynth CLI | FluidSynth 命令行 | ⭐⭐⭐⭐⭐ |
| 3 | pyfluidsynth | libfluidsynth 动态库 | ⭐⭐⭐⭐ |
| 4 | pretty_midi | 无需额外安装 | ⭐⭐ |

## 🎨 功能详解

### Web UI 界面

#### 创作面板

- **音乐描述** —— 输入自然语言描述（如："一段适合雨天听的忧伤钢琴曲"）
- **AI 推荐参数** —— 一键让 AI 根据描述推荐风格、调性、速度、乐器编配
- **参数调整** —— 手动微调风格（10种）、调性、速度（30-300 BPM）、拍号、小节数（4-64）
- **乐器选择** —— 标签式选择，内置 16 种常用乐器快捷按钮，支持全部 128 种 GM 乐器

#### Studio 编辑工作室

生成完成后可进入 Studio，提供五层渐进式编辑体验：

| 层级 | 功能 | 操作方式 |
|------|------|----------|
| 1. 一键预设 | 欢快/忧伤/激昂/平静/神秘/浪漫/紧张/史诗 | 点击按钮，AI 自动改编 |
| 2. 速度调节 | 实时调整 BPM | 拖动滑块，即时生效 |
| 3. 乐器轨道 | 查看各声部乐器 | 每轨独立 AI 改编按钮 |
| 4. 自由文本 | 自然语言描述修改意图 | 可指定段落范围 |
| 5. ABC 编辑器 | 直接编辑源码 | 双栏：编辑 + 实时预览 |

#### AI 听音诊断

基于多模态 LLM（如 Gemini）分析生成的音频文件：

- 🎧 **多模态分析** —— AI 实际"听"音频（base64 编码发送），而非仅分析谱面
- 📊 **评分系统** —— 1-10 分整体评价 + 星级显示
- 💡 **改进建议** —— 按严重度分级（critical/major/minor/suggestion）
- ⚡ **一键应用** —— 每条建议附带 `auto_fix_prompt`，点击即可让 AI 自动修改
- 🔄 **智能降级** —— 模型不支持音频输入时自动降级为谱面分析，UI 显示分析模式标识

#### 播放与下载

- 内置音频播放器（播放/暂停/停止/拖拽进度/音量控制）
- abcjs 五线谱渲染 + `TimingCallbacks` 光标同步
- 一键下载 MP3/WAV/MIDI 文件

## 📡 API 端点

共 22 个 RESTful 端点，基础路径 `/api`：

### 音乐生成

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/suggest-params` | AI 根据描述推荐音乐参数 |
| `POST` | `/generate` | 提交生成请求（快捷模式） |
| `GET` | `/status/{task_id}` | 查询任务状态 |
| `GET` | `/result/{task_id}` | 获取生成结果 |
| `GET` | `/download/{task_id}` | 下载音频文件 |
| `GET` | `/score/{task_id}` | 获取 ABC 乐谱 |
| `GET` | `/tasks` | 列出所有任务 |

### 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/projects` | 列出所有项目 |
| `POST` | `/projects` | 创建新项目 |
| `GET` | `/projects/{id}` | 获取项目详情 |
| `DELETE` | `/projects/{id}` | 删除项目 |
| `POST` | `/projects/{id}/generate` | 开始生成 |
| `POST` | `/projects/{id}/retry` | 从检查点重试 |
| `POST` | `/projects/{id}/refine` | AI 改编乐谱 |
| `PUT` | `/projects/{id}/score` | 手动编辑 ABC |
| `POST` | `/projects/{id}/audio-feedback` | AI 听音分析 |
| `GET` | `/projects/{id}/download/{type}` | 下载文件 |

### 系统设置

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/models` | 获取可用模型列表 |
| `GET` | `/settings` | 获取当前设置 |
| `PUT` | `/settings` | 更新设置 |
| `GET` | `/setup/fluidsynth` | FluidSynth 状态 |
| `POST` | `/setup/fluidsynth` | 安装 FluidSynth |
| `GET` | `/setup/soundfonts` | SoundFont 列表 |
| `POST` | `/setup/soundfonts` | 下载 SoundFont |

## 🧪 测试

```bash
# 运行全部测试
pytest tests/ -v

# 运行特定模块
pytest tests/test_conversion.py -v
pytest tests/test_generation.py -v
```

测试覆盖 6 个模块，共 39 个测试用例：

| 模块 | 测试内容 |
|------|----------|
| `test_api.py` | API 路由响应、参数验证、错误处理 |
| `test_config.py` | YAML 加载、默认值、路径解析 |
| `test_conversion.py` | ABC 解析、多声部、无效输入、MIDI 转换与时长 |
| `test_generation.py` | JSON 提取、代码块解析、空白处理、异常抛出 |
| `test_instrument_mapper.py` | 精确/模糊匹配、中文乐器名、通道分配、打击乐 |
| `test_schemas.py` | 请求模型默认值、边界校验、任务 ID 唯一性 |

## ⚙️ 配置说明

`config/settings.yaml` 支持以下配置项：

```yaml
ai:
  base_url: "https://api.openai.com/v1"  # LLM API 端点
  model: "gpt-4"                          # 模型名称
  max_retries: 3                          # 生成失败重试次数
  temperature: 0.8                        # 创意随机度 (0-2)

music:
  default_tempo: 120        # 默认速度 (BPM)
  default_key: "C"          # 默认调性
  default_time_signature: "4/4"
  default_style: "classical"
  max_measures: 64          # 最大小节数

synthesis:
  soundfont: "soundfonts/MuseScore_General.sf2"
  sample_rate: 44100        # 采样率
  output_format: "mp3"      # 默认输出格式

postprocess:
  reverb: true              # 混响开关
  reverb_room_size: 0.3     # 混响大小 (0-1)
  normalize: true           # 响度归一化
  fade_in_ms: 100           # 淡入时长 (ms)
  fade_out_ms: 500          # 淡出时长 (ms)

server:
  host: "0.0.0.0"
  port: 8000
  cors_origins:             # CORS 白名单
    - "http://localhost:3000"
```

API Key 通过 `.env` 文件配置（不纳入版本控制）：

```env
OPENAI_API_KEY=sk-xxxxx
```

优先级：运行时设置 > `.env` 文件 > 环境变量 `OPENAI_API_KEY`

## 📝 开发历程

### 第一阶段：核心管线搭建

1. **数据模型设计** —— 定义 `MusicRequest` → `ScoreResult` → `AudioResult` 完整数据流，使用 Pydantic v2 实现严格类型验证
2. **LLM 集成** —— 基于 OpenAI 兼容 API，实现自然语言到 ABC 记谱法的生成，支持任意 LLM 端点
3. **ABC → MIDI 转换** —— 使用 music21 解析 ABC 记谱法，实现 128 种 GM 乐器映射和自动 MIDI 通道分配
4. **音频合成** —— 集成 FluidSynth 进行专业级 SoundFont 采样合成，设计四级降级策略保证可用性
5. **音频后处理** —— 使用 Spotify 的 pedalboard 库构建处理链（混响 → 压缩 → 归一化 → 裁剪 → 格式转换）
6. **四阶段管线** —— 将生成流程编排为 Generating → Converting → Rendering → Postprocessing 四个阶段，支持断点恢复

### 第二阶段：Web 应用开发

7. **FastAPI 后端** —— 实现 22 个 RESTful 端点，异步任务执行，后台线程池处理耗时操作
8. **前端界面** —— 原生 HTML/CSS/JS 构建深色主题单页应用，集成 abcjs 实现五线谱可视化和光标同步
9. **项目管理** —— 基于文件系统的项目持久化（`projects/{uuid}/project.json`），完整 CRUD 管理
10. **环境自动化** —— Web UI 内一键安装 FluidSynth、下载 SoundFont，零命令行配置

### 第三阶段：智能编辑与反馈

11. **Studio 编辑工作室** —— 五层渐进式编辑体验，从一键预设到 ABC 源码编辑，满足不同深度的编辑需求
12. **AI 改编** —— `refine()` 方法支持自然语言描述修改意图，AI 在现有乐谱基础上改编
13. **AI 参数推荐** —— `suggest_params()` 从描述自动推荐风格、调性、速度、乐器编配
14. **AI 听音诊断** —— 多模态音频分析（Gemini `input_audio`），支持降级为谱面分析，评分 + 建议 + 一键应用

### 技术亮点

- **两步分离生成** —— 元数据 JSON 与 ABC 纯文本分步生成，避免 JSON 格式约束导致的乐谱截断
- **鲁棒的 ABC 解析** —— 启发式检测裸 ABC 文本、自动包装、结构验证、截断检测
- **多模态分析验证** —— 返回 `audio_analyzed` 标识和 token 用量日志，确认音频被实际分析
- **深度错误恢复** —— 编辑失败不丢失原有乐谱和音频，管线断点续作

## 📜 许可证

MIT License
