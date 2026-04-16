# 下载视频 + VAD / ASR + Qwen API 技能说明

## 技能目标

这个技能只关注一条最小可用链路：

1. 从 B 站下载视频或音频
2. 将音频转为统一格式
3. 基于时间戳进行切段（当前仓库更接近“按转写结果切片”，不是严格独立的 VAD 模块）
4. 调用 ASR 获得转写结果
5. 调用 Qwen API 对文本做进一步分析、标注或结构化生成

适合用于构建 `(text, voice)` 数据集，或做后续的大模型风格蒸馏、说话方式建模、文本知识抽取。

---

## 适用范围

本技能只整理以下能力：

- 下载视频 / 音频
- 音频预处理
- 切片 / 近似 VAD 流程
- ASR 转写
- Qwen API 调用

不包含以下内容：

- Cookie 以外的登录安全细节
- Telegram 群组搜索 / 监听
- 报告系统
- 训练脚本本身
- 声纹克隆 / TTS 训练

---

## 目录中与本技能有关的脚本

### 1. `tools/convert_bili_cookies.py`
作用：

- 将浏览器导出的 B 站 cookie JSON
- 转为 `yt-dlp` 可直接读取的 Netscape cookies 文本

用途：

- 为下载 B 站内容提供登录态支持
- 减少下载失败、权限不足、限流等问题

### 2. `tools/bili_batch_download.sh`
作用：

- 按 `bili_urls.txt` 中的链接批量下载 B 站视频
- 使用归档文件避免重复下载

用途：

- 适合先囤原始素材
- 适合已经明确有一批视频链接的情况

### 3. `tools/run_one_unit.py`
作用：

- 从一个 B 站合辑中拿 1 个视频
- 下载音频
- 转成 16k wav
- 调用 Fun-ASR 转写
- 生成 transcript、segments、meta 等中间结果

用途：

- 最适合先验证链路是否跑通
- 推荐先跑单个 unit，再扩展批量处理

### 4. `tools/split_unit_pairs.py`
作用：

- 根据单个 unit 的时间戳结果
- 将整段 wav 切成多个 `(text, voice)` 小样本

用途：

- 将长音频拆成训练用短片段
- 生成 `pairs.jsonl` 和切片 wav

说明：

- 从你贴出的说明看，这一步核心依据是“时间戳切片”
- 因此它更接近“基于 ASR 对齐结果的切段”
- 严格来说不一定是独立 VAD 模型先验切分

### 5. `tools/batch_build_pairs_dataset.py`
作用：

- 批量拉取视频
- 对每个视频做转写和切片
- 汇总进入统一数据集目录
- 删除单视频中间文件

用途：

- 在单元流程跑通后，用于批量构建数据集
- 适合正式积累训练数据

---

## 整体流程

### 路线 A：先验证单个视频是否跑通

```bash
DASHSCOPE_API_KEY="你的key" \
python3 /root/autodl-tmp/big_yellow_distill/tools/run_one_unit.py \
  --playlist-url "https://space.bilibili.com/267068018/lists/7834132?type=season"
```

这一步完成后，你会得到：

- 下载得到的音频 wav
- 一整段 transcript
- 带时间戳的 `segments.json`
- `meta.json`

然后再执行：

```bash
python3 /root/autodl-tmp/big_yellow_distill/tools/split_unit_pairs.py \
  --unit-dir /root/autodl-tmp/big_yellow_distill/unit_outputs/<timestamp>
```

这样就能把单条长音频拆成多个 `(text, voice)` 样本。

### 路线 B：直接批量构建数据集

```bash
DASHSCOPE_API_KEY="你的key" \
python3 /root/autodl-tmp/big_yellow_distill/tools/batch_build_pairs_dataset.py \
  --base-dir /root/autodl-tmp/big_yellow_distill \
  --max-videos 8 \
  --max-duration 420 \
  --min-sec 1.2 \
  --max-sec 10.0 \
  --enhance-vocals
```

这一步会：

1. 顺序处理多个视频
2. 每个视频先下载
3. 转写
4. 切片
5. 结果汇总到 `pairs_dataset/`
6. 删除单视频的中间目录

---

## 模块一：下载视频 / 音频

### 目标

将 B 站素材稳定落地到本地，供后续转写和切片使用。

### 依赖

- `yt-dlp`
- `ffmpeg`
- 可选：B 站 cookies

安装：

```bash
python3 -m pip install -U yt-dlp
```

### Cookie 转换

```bash
python3 /root/autodl-tmp/big_yellow_distill/tools/convert_bili_cookies.py \
  /root/autodl-tmp/big_yellow_distill/bilibili_cookies.json \
  /root/autodl-tmp/big_yellow_distill/bilibili_cookies.txt
```

作用：

- 将浏览器导出的 JSON cookie 转为 `yt-dlp` 能直接读取的文本 cookie

### 批量下载

编辑 `bili_urls.txt`，每行一个链接，然后执行：

```bash
bash /root/autodl-tmp/big_yellow_distill/tools/bili_batch_download.sh
```

或者：

```bash
bash /root/autodl-tmp/big_yellow_distill/tools/bili_batch_download.sh \
  /path/to/cookies.json \
  /path/to/bili_urls.txt \
  /path/to/output_dir
```

### 下载阶段的建议

1. 先保证登录态可用，再批量下载。
2. 使用归档文件去重，避免重复下载。
3. 尽量优先保存音频可用的原始素材，便于后续重复切片。
4. 对主播数据集来说，优先选单人说话清晰、背景人声少的视频。

---

## 模块二：VAD / 切片

## 当前仓库里的实际做法

从你给的说明看，当前流程更偏向：

- 先做 ASR
- 再根据 `segments.json` 中的时间戳
- 把长 wav 切成多个较短片段

对应脚本：

```bash
python3 /root/autodl-tmp/big_yellow_distill/tools/split_unit_pairs.py \
  --unit-dir /root/autodl-tmp/big_yellow_distill/unit_outputs/<timestamp>
```

### 默认产物

- `unit_outputs/<timestamp>/clips/*.wav`
- `unit_outputs/<timestamp>/pairs.jsonl`
- 全局 `clip_manifest.jsonl`

### 常用参数

- `--min-sec`：最短片段时长，默认 `1.5`
- `--max-sec`：目标最长片段时长，默认 `12.0`
- `--global-manifest`：指定全局清单路径
- `--skip-global-manifest`：不追加全局清单

### 这个阶段可以怎样理解为“VAD”

严格来说：

- 真正的 VAD 一般是直接基于声音能量、停顿、语音边界做切分
- 而当前仓库说明里更明确的是“基于转写时间戳切片”

所以更准确的说法是：

- 当前技能支持“按 ASR 段落边界切片”
- 若要做更强的 VAD，可在这一步之前接入独立 VAD 模块

### 实战建议

对于主播语音数据：

1. `min-sec` 不宜太短，否则容易切成语气词、半句话。
2. `max-sec` 不宜太长，否则训练时一条样本信息密度过高、语气混杂。
3. 常用区间可以是 `1.2 ~ 10s` 或 `1.5 ~ 12s`。
4. 如果目标是训练说话风格，尽量让每条样本只保留一个相对完整的口语单元。
5. 背景音乐较重时，可配合 `--enhance-vocals` 做人声增强。

---

## 模块三：ASR 转写

### 当前使用方式

单视频转写主流程：

```bash
DASHSCOPE_API_KEY="你的key" \
python3 /root/autodl-tmp/big_yellow_distill/tools/run_one_unit.py \
  --playlist-url "https://space.bilibili.com/267068018/lists/7834132?type=season"
```

说明中提到的默认模型：

- `fun-asr-realtime`

### 输入输出

输入：

- 下载后的音频
- 会被统一转成 `16k wav`

输出：

- `transcript.txt`
- `segments.json`
- `meta.json`

其中最关键的是：

- `transcript.txt`：整段文字结果
- `segments.json`：带时间戳的分段结果，用于后续切片

### 常用参数

- `--model`：Fun-ASR 模型名，默认 `fun-asr-realtime`
- `--keep-raw-audio`：保留下载下来的原始音频文件

### ASR 阶段建议

1. 统一转成 16k wav，减少后续兼容问题。
2. 先检查转写质量，再决定是否批量跑。
3. 游戏直播、多人语音、背景音乐会显著影响转写质量。
4. 若你的目标是训练“口头风格”，ASR 后最好还有一层文本清洗。
5. 最关键的是保留好时间戳，因为后续切片完全依赖它。

---

## 模块四：调用 Qwen API

### 这个模块的定位

Qwen API 更适合做 ASR 之后的“文本理解与标注增强”，例如：

- 生成摘要
- 提取主要内容
- 标注情绪类别
- 标注情绪强度
- 判断碎嘴程度
- 生成结构化 JSON
- 过滤无效样本
- 改写 ASR 噪声文本为更自然的口语文本

### 你贴出的说明里对应的用法

在 Telegram 那部分说明中，Qwen API 的作用是：

- 根据 `detector_description.txt`
- 对历史消息或实时消息做检测
- 输出报告

这个思路可以直接迁移到主播语音数据集构建中：

- 将 ASR 文本输入 Qwen
- 让 Qwen 生成结构化标签
- 再把这些标签写入训练样本

### 推荐的调用位置

最适合放在下面两个位置之一：

#### 方案 A：在 ASR 之后、切片之前

用途：

- 先对整段文本做总结
- 判断该视频是否值得继续切片

适合：

- 粗筛视频
- 过滤多人对话、内容过杂、非目标风格视频

#### 方案 B：在切片之后，对每个 `(text, voice)` 样本调用

用途：

- 给每条样本生成标签
- 为后续蒸馏训练准备监督字段

适合：

- 构建高质量训练集
- 训练带条件控制的风格模型

### 推荐的结构化输出字段

对于主播语料，推荐至少生成这些字段：

```json
{
  "主要内容": "一句话概括主播在说什么",
  "情绪类别": "愤怒/吐槽/疑问互动/兴奋/平静/阴阳怪气/搞怪",
  "情绪强度": 1,
  "碎嘴程度": 1,
  "是否适合训练": true,
  "噪声说明": "是否存在口误、截断、多人串音、ASR错误"
}
```

### Qwen API 的提示词建议

对于单条样本，可以让模型完成：

1. 修正明显 ASR 错字，但尽量保持口语风格
2. 输出一句话主要内容
3. 输出情绪标签
4. 输出强度分级
5. 输出碎嘴程度
6. 判断该样本是否适合训练

一个可复用的提示模板可以写成：

```text
你是一个中文口语语料标注助手。

请根据下面的 ASR 文本，完成以下任务：
1. 修正明显识别错误，但尽量保持原始口语风格，不要改写得过于书面。
2. 用一句话概括主要内容。
3. 判断情绪类别。
4. 给出情绪强度（1~5）。
5. 给出碎嘴程度（1~5）。
6. 判断这条样本是否适合用于“主播说话风格模仿训练”。
7. 输出 JSON，不要输出额外解释。

ASR文本：
{{text}}
```

### 使用建议

1. 不要一开始就把 Qwen 放到全量流程里，先人工检查几十条样本。
2. 尽量要求模型输出严格 JSON，方便后处理。
3. 对高噪音文本，可先做一次粗清洗，再交给 Qwen。
4. 若样本很多，优先把 Qwen 用在筛选和标注上，而不是所有文本都重写一遍。

---

## 推荐的最小可用流程

### 方案 1：最稳妥

1. 用 `run_one_unit.py` 跑 1 个视频
2. 检查 `transcript.txt` 和 `segments.json`
3. 用 `split_unit_pairs.py` 切片
4. 抽查 `clips/*.wav` 与文本对齐情况
5. 再用 Qwen 给样本补标签

### 方案 2：正式批量

1. 用 `batch_build_pairs_dataset.py` 批量处理视频
2. 开启 `--enhance-vocals`
3. 对生成的 `pairs_manifest.jsonl` 再跑一层 Qwen 标注
4. 清理多人串音、笑声过多、语义不完整样本

---

## 输出结果建议

如果你要把这一套最终沉淀为训练集，建议每条样本至少保留：

```json
{
  "id": "视频ID_片段序号",
  "audio_path": "clips/xxx.wav",
  "asr_text": "原始转写文本",
  "text_corrected": "清洗后的口语文本",
  "start": 0.0,
  "end": 3.2,
  "duration": 3.2,
  "instruct": {
    "主要内容": "...",
    "情绪类别": "...",
    "情绪强度": 3,
    "碎嘴程度": 2
  },
  "trainable": true
}
```

这样后面既可以做：

- 纯 TTS / 语音克隆数据
- 文本风格蒸馏
- 条件控制生成
- 情绪分类或风格分类

---

## 常见问题

### 1. `DASHSCOPE_API_KEY is not set`

说明没有设置环境变量。

示例：

```bash
DASHSCOPE_API_KEY="你的key" python3 xxx.py
```

### 2. `ffmpeg: command not found`

说明系统里没有安装 `ffmpeg`。

### 3. `yt-dlp` 报错

先升级：

```bash
python3 -m pip install -U yt-dlp
```

### 4. 切片效果不好

优先检查：

- 原始音频是否多人说话
- ASR 时间戳是否稳定
- `min-sec` / `max-sec` 是否过于激进

### 5. Qwen 输出不稳定

优先检查：

- prompt 是否要求“只输出 JSON”
- 示例是否足够明确
- 输入文本是否噪音过大

---

## 一句话总结

这套技能的核心不是“下载完就结束”，而是建立一条可复用的数据生产链：

- 用 `yt-dlp` 稳定拿到素材
- 用 ASR 获得文字和时间戳
- 用切片流程把长音频拆成训练样本
- 用 Qwen API 给样本补充结构化标签

最终目标是把原始视频，变成高质量、可训练、可筛选、可扩展的 `(text, voice)` 数据集。
