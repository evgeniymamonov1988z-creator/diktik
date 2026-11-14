# Тест точности распознавания Диктика.
# Берём записи русской речи с эталонным текстом (Google FLEURS, CC-BY 4.0),
# склеиваем в «диктовку» с паузами и прогоняем через ту же логику, что в
# diktik.py (нарезка на фразы по громкости -> faster-whisper), с разными
# настройками. Считаем WER (долю ошибочных слов) и скорость.
import os
import re
import csv
import json
import time
import random
import tarfile
import urllib.request

import numpy as np
import soundfile as sf
import jiwer
from faster_whisper import WhisperModel

SR = 16000
BLOCK = 4000                 # как в Диктике: 0.25 с
SILENCE_LEVEL = 0.0010       # как в Диктике
N_UTT = int(os.environ.get("N_UTT", "40"))
BASE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/ru_ru"

HALLUCINATIONS = [
    "редактор субтитров", "субтитры создавал", "субтитры сделал", "корректор",
    "продолжение следует", "спасибо за просмотр", "подписывайтесь на канал",
    "subtitles by", "subscribe", "thanks for watching", "amara.org", "транскрибация",
]


def log(*a):
    print(*a, flush=True)


def download(url, path):
    if not os.path.exists(path):
        log("скачиваю", url)
        urllib.request.urlretrieve(url, path)


# ---------------------------------------------------------------- данные
def load_data():
    download(BASE + "/test.tsv", "test.tsv")
    download(BASE + "/audio/test.tar.gz", "test.tar.gz")
    rows = []
    with open("test.tsv", encoding="utf-8") as fh:
        for r in csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(r) >= 3:
                rows.append((r[0], r[1], r[2]))   # id, файл, исходный текст
    # по одной записи на предложение, случайные дикторы
    random.seed(1)
    random.shuffle(rows)
    seen, chosen = set(), []
    for sid, fname, text in rows:
        if sid in seen:
            continue
        seen.add(sid)
        chosen.append((fname, text))
        if len(chosen) >= N_UTT:
            break
    want = {f for f, _ in chosen}
    audio = {}
    with tarfile.open("test.tar.gz", "r:gz") as tar:
        for m in tar:
            b = os.path.basename(m.name)
            if b in want:
                f = tar.extractfile(m)
                a, sr = sf.read(f, dtype="float32")
                if a.ndim > 1:
                    a = a.mean(axis=1)
                assert sr == SR, sr
                audio[b] = a
    chosen = [(audio[f], t) for f, t in chosen if f in audio]
    log("записей:", len(chosen))
    return chosen


def build_stream(chosen, noise_std, seed=7):
    rng = np.random.default_rng(seed)
    parts, refs = [], []
    for a, t in chosen:
        parts.append(a)
        refs.append(t)
        parts.append(np.zeros(int(SR * rng.uniform(0.7, 1.6)), np.float32))
    s = np.concatenate(parts).astype(np.float32)
    s = s + rng.normal(0, noise_std, len(s)).astype(np.float32)
    return s, " ".join(refs)


# ---------------------------------------------------------------- логика Диктика
def segment(stream, end_sil, max_phrase, adaptive):
    """Нарезка на фразы — повтор Recognizer._process_loop/_flush_phrase."""
    out = []
    phrase, sil, speaking = [], 0, False
    end_need, max_need = int(SR * end_sil), int(SR * max_phrase)
    levels = []

    def thr():
        if not adaptive or len(levels) < 4:
            return SILENCE_LEVEL
        floor = float(np.percentile(levels[-32:], 10))   # фон за ~8 с
        return max(SILENCE_LEVEL, floor * 2.5)

    def flush(ph, t):
        if not ph:
            return
        a = np.concatenate(ph)
        if float(np.abs(a).mean()) < t or len(a) / SR < 0.3:
            return
        peak = float(np.max(np.abs(a)))
        if peak > 0:
            a = (a * min(0.95 / peak, 40.0)).astype(np.float32)
        out.append(a)

    for i in range(0, len(stream), BLOCK):
        d = stream[i:i + BLOCK]
        lvl = float(np.abs(d).mean())
        levels.append(lvl)
        t = thr()
        if lvl >= t:
            speaking, sil = True, 0
            phrase.append(d)
        elif speaking:
            phrase.append(d)
            sil += len(d)
            if sil >= end_need:
                flush(phrase, t)
                phrase, speaking, sil = [], False, 0
        if sum(len(p) for p in phrase) >= max_need:
            flush(phrase, t)
            phrase, speaking, sil = [], False, 0
    flush(phrase, thr())
    return out


def transcribe(model, audio, lang, beam, prompt):
    segs, info = model.transcribe(
        audio, language=lang, beam_size=beam, temperature=0.0,
        vad_filter=True, no_speech_threshold=0.6,
        compression_ratio_threshold=10.0, condition_on_previous_text=False,
        initial_prompt=prompt or None,
    )
    parts = []
    for s in segs:
        if getattr(s, "no_speech_prob", 0.0) > 0.6:
            continue
        if getattr(s, "avg_logprob", 0.0) < -1.5:
            continue
        x = s.text.strip()
        if any(h in x.lower() for h in HALLUCINATIONS):
            continue
        if x:
            parts.append(x)
    return " ".join(parts).strip(), getattr(info, "language", "?")


def norm(s):
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- прогон
CONFIGS = [
    dict(key="A", name="Как было (small, пауза 0.35 с, фраза ≤5 с, beam 1, язык ru)",
         model="small", end=0.35, maxp=5, beam=1, lang="ru", prompt=False, adaptive=False),
    dict(key="N", name="Новый Диктик (small, пауза 0.9 с, фраза ≤15 с, beam 5, контекст)",
         model="small", end=0.9, maxp=15, beam=5, lang="ru", prompt=True, adaptive=False),
    dict(key="T", name="То же на large-v3-turbo",
         model="large-v3-turbo", end=0.9, maxp=15, beam=5, lang="ru", prompt=True, adaptive=False),
]
NOISY_KEYS = {"A", "N", "T"}
models = {}


def get_model(name):
    if name not in models:
        log("загружаю модель", name)
        models[name] = WhisperModel(name, device="cpu", compute_type="int8",
                                    cpu_threads=os.cpu_count() or 4)
    return models[name]


def run(cfg, stream, ref):
    m = get_model(cfg["model"])
    phrases = segment(stream, cfg["end"], cfg["maxp"], cfg["adaptive"])
    texts, langs = [], {}
    t0 = time.time()
    for a in phrases:
        prompt = " ".join(texts)[-200:] if cfg["prompt"] else None
        txt, lg = transcribe(m, a, cfg["lang"], cfg["beam"], prompt)
        langs[lg] = langs.get(lg, 0) + 1
        if txt:
            texts.append(txt)
    dt = time.time() - t0
    hyp = " ".join(texts)
    wer = jiwer.wer(norm(ref), norm(hyp))
    plen = [len(a) / SR for a in phrases]
    return dict(key=cfg["key"], name=cfg["name"], wer=round(wer * 100, 1),
                phrases=len(phrases), avg_phrase_s=round(float(np.mean(plen)), 1) if plen else 0,
                rtf=round(dt / (len(stream) / SR), 3), seconds=round(dt, 1),
                langs=langs, sample=hyp[:600])


def main():
    chosen = load_data()
    variants = {
        "тихий фон": build_stream(chosen, noise_std=0.0004),
        "шумный микрофон": build_stream(chosen, noise_std=0.002),
    }
    results = []
    for vname, (stream, ref) in variants.items():
        log(f"=== {vname}: {len(stream)/SR/60:.1f} мин звука")
        for cfg in CONFIGS:
            if vname != "тихий фон" and cfg["key"] not in NOISY_KEYS:
                continue
            r = run(cfg, stream, ref)
            r["variant"] = vname
            results.append(r)
            log(f"[{vname}] {r['key']}: WER={r['wer']}%  фраз={r['phrases']} "
                f"ср.фраза={r['avg_phrase_s']}с  RTF={r['rtf']}  языки={r['langs']}")
    ref_quiet = variants["тихий фон"][1]

    md = ["## Точность распознавания Диктика (FLEURS ru, %d записей)" % len(chosen), "",
          "| Звук | Вариант | Ошибок слов (WER) | Фраз | Ср. длина фразы | Время / длит. звука |",
          "|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['variant']} | {r['name']} | **{r['wer']}%** | {r['phrases']} | "
                  f"{r['avg_phrase_s']} с | {r['rtf']} |")
    md += ["", "### Начало текста", "", "**Эталон:** " + ref_quiet[:600], ""]
    for r in results:
        if r["variant"] == "тихий фон":
            md.append(f"**{r['key']}:** {r['sample']}")
            md.append("")
    text = "\n".join(md)
    log(text)
    with open("results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
