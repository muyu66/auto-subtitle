# auto-subtitle

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

把视频或音频文件拖进终端，自动完成：

**提取音频 → 本地语音识别（中文为主、多语种支持）→ 导出 SRT 字幕**

识别全程在本机完成，音视频文件不会上传到任何服务器。模型下载一次后可完全离线使用。

## 功能特点

- **拖放即用**：把文件拖进终端窗口，回车开始；支持一次拖入多个文件
- **两种识别引擎**：SenseVoice（中文专用）与 faster-whisper（多语种通用）
- **完全本地**：音频提取与语音识别都在本机运行，保护隐私
- **自动断句**：按中英文标点断句，长句自动拆分，时间轴按文字量分配
- **模型管理**：首次使用自动下载并支持断点续传，优先 ModelScope，失败自动回退 Hugging Face / hf-mirror
- **实用参数**：热词、固定错词替换、静音检测（VAD）、GPU 加速、自定义模型
- **输出灵活**：SRT / 纯文本，UTF-8 编码，常见播放器可直接加载

## 快速开始（Windows）

### 1. 安装 Python

安装 [Python 3.9 或更高版本](https://www.python.org/downloads/)，安装时勾选 **Add Python to PATH**。

### 2. 安装 FFmpeg

任选一种方式：

- 在终端执行 `winget install Gyan.FFmpeg`
- 或从 <https://www.gyan.dev/ffmpeg/builds/> 下载，把 `bin` 目录加入 `PATH`

安装完成后重新打开终端，执行 `ffmpeg -version` 能正常输出即可。

### 3. 获取项目

```bat
git clone <仓库地址>
cd auto-subtitle
```

也可以直接在 GitHub 页面点击 **Code → Download ZIP**，解压后进入目录。

### 4. 安装依赖（只需一次）

双击 **`安装依赖.bat`**。脚本会自动创建 `.venv` 虚拟环境并安装所需依赖。

### 5. 开始使用

双击 **`运行.bat`**，然后：

1. 在模型列表里输入序号选择模型（直接回车使用默认的 Whisper turbo）
2. 把视频/音频文件从资源管理器拖进黑色窗口（可一次拖多个），按回车
3. 等待识别完成，字幕文件会生成在视频旁边

```text
==============================================================
  auto-subtitle  视频字幕生成工具  v1.0.0
  视频 → 提取音频 → 本地语音识别 → 导出 SRT 字幕
==============================================================
提示：把视频/音频文件直接拖到本窗口，按回车开始。
      可以一次拖入多个文件；输入 m 切换识别模型，输入 q 退出。

请选择识别模型（直接回车使用当前模型）：
  → 1. SenseVoice 中文专用      约 228 MB  中文口语更稳，速度快，自带标点
    2. Whisper turbo          约 1.6 GB  多语种通用，句子连贯，CPU 速度较快
    ...

请拖入文件（可多个），按回车开始；输入 m 切换模型，输入 q 退出：
> "C:\videos\我的视频.mp4"
```

识别完一个文件后，输入 **`m`** 可以换模型再试一次，方便对比不同模型的效果。

## 手动安装（Linux / macOS / 自定义环境）

```bash
git clone <仓库地址>
cd auto-subtitle

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 或安装为命令：pip install -e .
```

运行：

```bash
python main.py "video.mp4"
# 或安装后使用命令
auto-subtitle "video.mp4"
```

> 需要系统已安装 `ffmpeg` 与 `ffprobe`（macOS：`brew install ffmpeg`；
> Ubuntu/Debian：`sudo apt install ffmpeg`）。

## 命令行用法

```bat
:: 直接处理文件
运行.bat "D:\videos\a.mp4"

:: 批量处理并指定输出目录
运行.bat "a.mp4" "b.mp4" -o "D:\字幕"

:: 同时导出 SRT 和纯文本
运行.bat "a.mp4" --format both

:: 使用更快的模型
运行.bat "a.mp4" --model small

:: 使用中文专用的 SenseVoice
运行.bat "a.mp4" --engine sensevoice

:: 加入专有名词热词（仅 Whisper）
运行.bat "a.mp4" --hotwords "人名 地名 专有名词 C4"

:: 批量修正固定错词
运行.bat "a.mp4" --replace "错词=正确词,错词2=正确词2"

:: 查看全部模型
运行.bat --list-models
```

在 Linux / macOS 上把 `运行.bat` 换成 `python main.py` 即可。

### 参数说明

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--engine` | 识别引擎：`auto` / `whisper` / `sensevoice` | `auto`（等同 whisper） |
| `-m, --model` | Whisper 模型：`tiny` / `base` / `small` / `medium` / `large-v3` / `turbo`，也可填仓库名或本地目录 | `turbo` |
| `--hotwords` | 热词（人名、地名、术语），空格或逗号分隔，仅 Whisper 生效 | 无 |
| `--replace` | 识别结果替换，格式 `错词=正确词,错词2=正确词2` | 无 |
| `--model-source` | Whisper 模型下载源：`auto` / `modelscope` / `hf` | `auto`（优先 ModelScope） |
| `-l, --language` | 语言代码，如 `zh`、`en`；留空自动检测 | 自动检测 |
| `-o, --output-dir` | 字幕输出目录 | 与媒体文件同目录 |
| `-f, --format` | 输出格式：`srt` / `txt` / `both` | `srt` |
| `--max-chars` | 每条字幕最大字符数（最小 8） | `30` |
| `--beam-size` | 束搜索宽度，越大越准但越慢 | `5` |
| `--threads` | CPU 线程数 | 自动（最多 8） |
| `--device` | 计算设备：`auto` / `cpu` / `cuda` | `auto` |
| `--compute-type` | 计算精度，如 `int8`、`float16` | CPU 用 `int8`，GPU 用 `float16` |
| `--initial-prompt` | 自定义识别引导提示 | 中文提示 |
| `--no-prompt` | 关闭中文引导提示（纯英文内容可用） | 提示开启 |
| `--no-vad` | 关闭静音检测 | 开启 |
| `--overwrite` | 覆盖同名输出文件 | 自动改名，不覆盖 |
| `--list-models` | 列出可选模型后退出 | — |
| `--version` | 显示版本号 | — |

## 模型怎么选

交互模式启动时会显示模型列表；识别过程中输入 `m` 可随时切换模型。
也可以用 `运行.bat --list-models` 查看完整列表。

| 模型 | 大小 | 特点 |
| --- | --- | --- |
| **SenseVoice 中文专用** | 约 228 MB | 中文口语更稳、抗噪、自带标点，速度最快 |
| **Whisper turbo**（默认） | 约 1.6 GB | 精度接近 large-v3，CPU 速度较快，多语种通用 |
| Whisper large-v3 | 约 3.1 GB | 准确率最高，CPU 上较慢 |
| Whisper medium | 约 1.5 GB | 精度与速度折中 |
| Whisper small | 约 480 MB | 更快，适合长视频或低配电脑 |
| Whisper base | 约 145 MB | 只建议用于快速测试流程 |
| Whisper tiny | 约 75 MB | 仅用于验证流程 |

建议中文口语视频先用 **SenseVoice** 跑一遍，再用 **Whisper turbo** 跑一遍，
选择语句更通顺、断句更自然的结果。

### 模型下载与缓存

- Whisper 模型默认从 **ModelScope** 下载（国内速度更快）；失败时自动回退
  **Hugging Face**。Hugging Face 无法直连时会自动改用 `https://hf-mirror.com` 镜像。
- 所有下载均支持断点续传，中断后重新运行会继续下载。
- 模型缓存位置：
  - ModelScope / SenseVoice（Windows）：`%LOCALAPPDATA%\auto-subtitle\models`
  - ModelScope / SenseVoice（Linux / macOS）：`$XDG_CACHE_HOME/auto-subtitle/models`
    或 `~/.cache/auto-subtitle/models`
  - Hugging Face：`~/.cache/huggingface/hub`
- 下载完成后可断网离线使用。也可手动设置镜像：

```bat
set HF_ENDPOINT=https://hf-mirror.com
运行.bat "a.mp4" --model-source hf
```

使用 `--model <本地模型目录>` 可以加载自行转换的 faster-whisper 模型。

## 输出说明

- 默认生成与媒体文件同名的 `.srt` 字幕，UTF-8 编码。
- 同名文件已存在时不会覆盖，会生成 `视频名.1.srt`、`视频名.2.srt`……
  需要覆盖时加 `--overwrite`。
- `--format txt` 额外导出无时间轴的纯文本；`both` 两种都导出。
- 字幕按标点断句；单条过长时按逗号或长度自动拆分，时间按文字量分配。
- 临时音频文件在识别完成后自动删除。

## 识别效果不理想时

1. **换模型**：中文口语优先尝试 SenseVoice；追求最高精度可用 `large-v3`。
2. **加热词**：把人名、地名、专业术语写进 `--hotwords`（仅 Whisper）：

   ```bat
   运行.bat "a.mp4" --hotwords "张三 李四 专有名词 C4"
   ```

3. **修正固定错词**：已知的固定错法用 `--replace` 批量替换：

   ```bat
   运行.bat "a.mp4" --replace "错词=正确词,错词2=正确词2"
   ```

4. **改善录音**：背景音乐、音效与人声混在一起时会明显影响识别。
   如果条件允许，让人声单独占一条音轨，并保留约 6 dB 余量避免削波。
5. **调整语言**：中英混合内容可尝试 `--language zh`；纯英文内容加
   `--no-prompt` 可避免中文引导提示干扰。

## 常见问题

**找不到 ffmpeg**

安装 ffmpeg 后需要重新打开终端或重新双击 `运行.bat`，让新的 `PATH` 生效。
执行 `ffmpeg -version` 和 `ffprobe -version` 均应能正常输出。

**模型下载失败**

默认先从 ModelScope 下载，失败自动回退 Hugging Face。可检查网络，或用
`--model-source modelscope` / `--model-source hf` 指定下载源。下载中断后
重新运行会自动续传；也可以先在能联网的电脑上下载模型，再复制缓存目录。

**识别出来是繁体字**

默认的 `turbo` / `large-v3` 一般输出简体。若仍出现繁体，可改用 SenseVoice
（`--engine sensevoice`），或用 `--initial-prompt "以下是普通话的句子。"` 引导。

**SenseVoice 模型下载慢或失败**

它从 Hugging Face 镜像下载（约 228 MB，支持断点续传）。网络不稳定时重新运行
会继续下载；也可以先用默认的 Whisper 引擎。下载完成后位于
`%LOCALAPPDATA%\auto-subtitle\models\sensevoice`。

**视频没有声音**

没有音频轨道的文件会直接提示错误，不会生成空字幕。

**速度太慢**

CPU 推理速度取决于视频时长和电脑性能。可以换用 `--model small`、把
`--beam-size` 调为 `1`、减少 `--threads` 之外的 CPU 占用，或使用支持 CUDA 的
显卡（`--device cuda`）。

## 支持的格式

常见视频：`.mp4` `.mkv` `.mov` `.avi` `.flv` `.webm` `.wmv` `.m4v` `.ts` `.m2ts` 等

常见音频：`.mp3` `.wav` `.m4a` `.aac` `.flac` `.ogg` `.opus` `.wma` 等

其他格式也会尝试交给 ffmpeg 读取。

## 项目结构

```text
auto-subtitle/
├── main.py                   入口
├── auto_subtitle/
│   ├── __init__.py           版本号
│   ├── cli.py                命令行参数、交互流程、进度显示
│   ├── catalog.py            可选模型列表
│   ├── media.py              路径解析、ffmpeg 音频提取
│   ├── asr.py                faster-whisper 模型加载与识别
│   ├── sensevoice.py         SenseVoice 中文引擎 + Silero VAD
│   ├── model_store.py        ModelScope / HF 模型下载（断点续传）
│   ├── subtitles.py          断句、时间分配、SRT / TXT 生成
│   └── assets/
│       └── silero_vad.onnx   静音检测模型
├── tests/                    单元测试
├── 安装依赖.bat              Windows 一键安装依赖
├── 运行.bat                  Windows 启动脚本
├── requirements.txt          运行依赖
├── pyproject.toml            项目元数据与打包配置
├── LICENSE                   MIT 许可证
└── README.md
```

## 开发与测试

```bash
# Windows
.venv\Scripts\python.exe -m unittest discover -s tests -v

# Linux / macOS
.venv/bin/python -m unittest discover -s tests -v
```

测试只覆盖纯逻辑（路径解析、断句、时间轴、模型缓存判断等），不需要下载模型。

## 致谢

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 与
  [CTranslate2](https://github.com/OpenNMT/CTranslate2)：Whisper 高效推理
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)：SenseVoice 推理
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)：中文语音识别模型
- [Silero VAD](https://github.com/snakers4/silero-vad)：语音活动检测
- [FFmpeg](https://ffmpeg.org/)：音视频处理
- [ModelScope](https://www.modelscope.cn/) / [Hugging Face](https://huggingface.co/)：模型分发

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
