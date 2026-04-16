# Remi: 人格 + 记忆 + 情绪 的多模态 Agent (qwen3-vl-flash)

这是一个可直接运行的最小可用版本，目标是让 "AI 少女" 具备：

- 稳定人格（persona）
- 长短期记忆（SQLite）
- 情绪状态（valence/arousal）
- 原子工具调用（时间、联网搜索、记忆读写、图片理解）
- 自动摘要压缩（每 N 轮写入 summary）
- 三层分工架构（Heart / Body / Hippocampus）+ 心跳（Heartbeat）
- Milestone B：LTM 评分写入 + 关系状态 + 打扰预算/冷却

## 1) 快速开始

```bash
cd /Users/mabokai/Desktop/proj/Remi
python3 -m pip install -e .
```

配置 key（任选其一）：

```bash
export DASHSCOPE_API_KEY="你的key"
# 或
export QWEN_API_KEY="你的key"
```

然后启动：

```bash
ai-girl
```

单次提问：

```bash
ai-girl --once "你好，记住我喜欢二次元和摇滚"

# 触发一次心跳（可能选择沉默）
ai-girl --heartbeat-once
```

导出记忆快照：

```bash
ai-girl --export-memory data/memory_snapshot.json

# 清空本地记忆
ai-girl --reset-memory
```

## 2) 目录结构

- `src/ai_girl_agent/agent.py`: 总编排器（Heart/Body/Hippocampus/Heartbeat）
- `src/ai_girl_agent/heart.py`: 主观决策（回复草稿、i_wanna、i_think）
- `src/ai_girl_agent/body.py`: 执行控制（CLI 优先工具路由）
- `src/ai_girl_agent/hippocampus.py`: 记忆沉淀（摘要区/长期记忆）
- `src/ai_girl_agent/heartbeat.py`: 心跳调度与状态
- `src/ai_girl_agent/memory.py`: SQLite 记忆层
- `src/ai_girl_agent/emotion.py`: 情绪状态更新
- `src/ai_girl_agent/tools.py`: 原子工具集合
- `src/ai_girl_agent/persona.py`: 人设 prompt
- `src/ai_girl_agent/cli.py`: 命令行入口

## 3) 模型与接口

默认模型：`qwen3-vl-flash`

默认 Base URL：
`https://dashscope.aliyuncs.com/compatible-mode/v1`

可通过环境变量覆盖：

```bash
export AGENT_MODEL="qwen3-vl-flash"
export DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export SUMMARY_EVERY_N_TURNS=6
```

## 4) 内置原子工具

- `get_time`: 获取本地时间
- `web_search`: DuckDuckGo 文本搜索
- `remember`: 写入长期记忆
- `recall`: 读取长期记忆
- `vision_describe`: 本地图片路径描述

## 5) 目前是 MVP，下一步建议

1. 把记忆抽取从规则升级为 LLM+schema 抽取
2. 长期记忆检索改为向量召回（Qdrant/pgvector）
3. 增加反思器（失败后修正计划）
4. 给情绪增加更细粒度触发器与衰减机制
5. 增加观察性日志（token、延迟、工具命中率）

## 6) 事件与心跳状态

导出的 `memory_snapshot.json` 现在包含：

- `events`: 事件流（如 `user_message`、`heart_decision`、`body_result`、`heartbeat_tick`）
- `heartbeat_state`: 最近一次心跳状态（mode/idle_rounds/next_sleep_sec）
- `relation_state`: 关系状态（intimacy/trust/tension/closeness_label）
- `interruption_state`: 主动打扰预算与冷却（budget/cooldown_until/last_proactive_at）

用于排查“为什么这轮说话/沉默”、以及验证人格连续性与低打扰策略。
