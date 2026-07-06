#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地阿拉伯语字幕 SOP 流水线
用法:
  # 处理 inbox/ 里的所有视频/音频
  python3 run.py
  # 或指定单个文件
  python3 run.py "/path/to/video.mp4"

输出到 outputs/:
  <名字>.srt        字幕(毫秒级时间戳)
  <名字>.txt        纯文本
  <名字>.warnings.txt  需人工复查的告警(幻觉句/超长段/重复段)
"""
import sys
import os
import re
import wave
import shutil
import subprocess
import traceback
import av
from faster_whisper import WhisperModel

# ---------- 配置 ----------
# 模型：可为本地目录，或 faster-whisper 支持的规格名(如 "large-v3"，首次自动下载)。
# 复用本地已下载的模型：  export WHISPER_MODEL=/path/to/faster-whisper-large-v3
MODEL_PATH = os.environ.get("WHISPER_MODEL", "large-v3")
LANGUAGE = os.environ.get("WHISPER_LANG", "ar")
# 人声分离(可选)：背景音乐/音效重的视频建议开启，先用 Demucs 剥离人声再转录。
# 启用：  export SEPARATE_VOCALS=1   (需已 pip install demucs，首次会下载分离模型)
SEPARATE = os.environ.get("SEPARATE_VOCALS", "").strip().lower() not in ("", "0", "false", "no")
BASE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(BASE, "inbox")
OUTPUTS = os.path.join(BASE, "outputs")
MEDIA_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm",
             ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

# 已知幻觉/套话签名(命中则告警，不删除)
HALLUCINATION_HINTS = [
    "اشترك", "اشتركوا", "لا تنسوا", "لا تنسى", "شكرا للمشاهدة", "شكراً للمشاهدة",
    "المشاهدة", "الحلقة القادمة", "أراكم", "نانسي قنقر", "ترجمة", "بالتوفيق",
    "إلى اللقاء", "subscribe", "القناة",
]
LONG_SEG_SEC = 10.0  # 单段超过此时长视为可疑


def extract_wav(src, dst, rate=16000):
    container = av.open(src)
    stream = container.streams.audio[0]
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=rate)
    out = wave.open(dst, "wb")
    out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
    for frame in container.decode(stream):
        frame.pts = None
        for rf in resampler.resample(frame):
            out.writeframes(bytes(rf.planes[0]))
    for rf in resampler.resample(None):
        out.writeframes(bytes(rf.planes[0]))
    out.close(); container.close()


def separate_vocals(wav_path, workdir):
    """用 Demucs 分离人声，返回 vocals.wav 路径；失败/无产出返回 None。"""
    outdir = os.path.join(workdir, "_demucs")
    os.makedirs(outdir, exist_ok=True)
    cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", outdir, wav_path]
    subprocess.run(cmd, check=True)
    base = os.path.splitext(os.path.basename(wav_path))[0]
    vocals = os.path.join(outdir, "htdemucs", base, "vocals.wav")
    return vocals if os.path.exists(vocals) else None


def fmt_ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_one(model, src_path):
    name = os.path.splitext(os.path.basename(src_path))[0]
    wav_path = os.path.join(OUTPUTS, name + "_16k.wav")
    srt_path = os.path.join(OUTPUTS, name + ".srt")
    txt_path = os.path.join(OUTPUTS, name + ".txt")
    warn_path = os.path.join(OUTPUTS, name + ".warnings.txt")

    print(f"[1/3] 提取音频: {name}", file=sys.stderr)
    extract_wav(src_path, wav_path)

    asr_input = wav_path
    if SEPARATE:
        print(f"[1.5/3] 人声分离(Demucs)，首次会下载分离模型...", file=sys.stderr)
        try:
            vocals = separate_vocals(wav_path, OUTPUTS)
            if vocals:
                asr_input = vocals
                print(f"        已用分离后人声转录", file=sys.stderr)
            else:
                print(f"        分离未产出，回退到原音频", file=sys.stderr)
        except Exception as e:
            print(f"        分离失败({e})，回退到原音频", file=sys.stderr)

    print(f"[2/3] 转录(large-v3, 反幻觉参数)...", file=sys.stderr)
    segments, info = model.transcribe(
        asr_input,
        language=LANGUAGE,
        task="transcribe",
        beam_size=5,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        word_timestamps=True,
    )
    print(f"      检测语言: {info.language} (置信度={info.language_probability:.2f})", file=sys.stderr)

    print(f"[3/3] 写字幕 + 后处理告警...", file=sys.stderr)
    warnings = []
    prev_text = None
    repeat_count = 0
    with open(srt_path, "w", encoding="utf-8") as fs, open(txt_path, "w", encoding="utf-8") as ft:
        idx = 0
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            idx += 1
            fs.write(f"{idx}\n{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}\n{text}\n\n")
            ft.write(text + "\n")

            dur = seg.end - seg.start
            reasons = []
            if any(h in text for h in HALLUCINATION_HINTS):
                reasons.append("疑似幻觉/套话")
            if dur > LONG_SEG_SEC:
                reasons.append(f"超长段({dur:.0f}s)")
            if text == prev_text:
                repeat_count += 1
                if repeat_count == 1:
                    reasons.append("重复段")
            else:
                repeat_count = 0
            if reasons:
                warnings.append(f"#{idx} [{fmt_ts(seg.start)}] {'/'.join(reasons)}: {text}")
            prev_text = text

    with open(warn_path, "w", encoding="utf-8") as fw:
        if warnings:
            fw.write("以下段落需人工复查(未自动删除)：\n\n")
            fw.write("\n".join(warnings))
        else:
            fw.write("未发现明显可疑段落。")

    try:
        os.remove(wav_path)
    except OSError:
        pass
    shutil.rmtree(os.path.join(OUTPUTS, "_demucs"), ignore_errors=True)

    print(f"完成: {srt_path}", file=sys.stderr)
    print(f"      共 {idx} 段，告警 {len(warnings)} 处 -> {os.path.basename(warn_path)}", file=sys.stderr)
    return idx, len(warnings)


def main():
    os.makedirs(OUTPUTS, exist_ok=True)
    if len(sys.argv) >= 2:
        targets = [sys.argv[1]]
    else:
        targets = [os.path.join(INBOX, f) for f in sorted(os.listdir(INBOX))
                   if os.path.splitext(f)[1].lower() in MEDIA_EXT]
    if not targets:
        print("inbox/ 里没有可处理的媒体文件。把视频/音频丢进去再跑。", file=sys.stderr)
        return

    print(f"加载模型: {MODEL_PATH}", file=sys.stderr)
    model = WhisperModel(MODEL_PATH, device="cpu", compute_type="int8")

    for t in targets:
        if not os.path.exists(t):
            print(f"跳过(不存在): {t}", file=sys.stderr)
            continue
        try:
            transcribe_one(model, t)
        except Exception:
            print(f"处理失败: {t}", file=sys.stderr)
            traceback.print_exc()


if __name__ == "__main__":
    main()
