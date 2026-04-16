# Pipecat 本地部署记录（Remi）

项目目录：
- `/Users/mabokai/Desktop/proj/Remi/v1_0/remi_pipecat_openai/remi-pipecat`

## 你看到 404 的根因

你日志中的报错出现在说话开始后（`userStartedSpeaking`），这是 STT 链路触发时机。
我已复现并确认：

- `chat.completions` 在 DashScope OpenAI 兼容上可用
- 但 `audio/transcriptions`（STT）和 `audio/speech`（TTS）在该兼容端点会返回 `404`

所以同一个 `OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` 不能同时给 LLM + STT + TTS 使用。

## 我已做的修复

1. `bot.py` 支持分离配置：
   - LLM：`OPENAI_LLM_*`
   - STT：`OPENAI_STT_*`
   - TTS：`OPENAI_TTS_*`
2. 增加启动前校验：如果 STT/TTS 仍指向 DashScope，会直接抛出清晰错误，避免运行时反复 404。
3. `.env` 改成了分离模板。

## 现在怎么配

- 继续用 DashScope 做 LLM（已配置好）
- STT/TTS 改为支持 OpenAI 音频端点的服务（最直接是官方 OpenAI）

### 必填（示例）

```env
OPENAI_LLM_API_KEY=<你的 DashScope Key>
OPENAI_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_LLM_MODEL=qwen3.5-flash

OPENAI_STT_API_KEY=<支持 audio/transcriptions 的 key>
OPENAI_STT_BASE_URL=https://api.openai.com/v1
OPENAI_STT_MODEL=gpt-4o-transcribe

OPENAI_TTS_API_KEY=<支持 audio/speech 的 key>
OPENAI_TTS_BASE_URL=https://api.openai.com/v1
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_VOICE_ID=alloy
```

## 启动

```bash
cd /Users/mabokai/Desktop/proj/Remi/v1_0/remi_pipecat_openai/remi-pipecat/server
uv run bot.py
```

