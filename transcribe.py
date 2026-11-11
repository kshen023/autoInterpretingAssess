import os, json, time, hmac, base64, hashlib, urllib.parse, csv, secrets, string
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv
from mutagen import File as AudioFile

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "class 5"   # 你的录音文件夹
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")
APP_ID = os.getenv("XF_APP_ID")
API_KEY = os.getenv("XF_API_KEY")
API_SECRET = os.getenv("XF_API_SECRET")

BASE_URL = "https://office-api-ist-dx.iflyaisol.com"
POLL_INTERVAL = 10
MAX_WAIT_SECONDS = 5 * 60 * 60
SMOOTH = False
COLLOQUIAL = False
EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".pcm", ".speex"}

def now_string():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S%z")

def make_signature(params):
    parts = []
    for key, value in sorted(params.items()):
        if value is not None and str(value) != "":
            parts.append(f"{key}={urllib.parse.quote(str(value), safe='')}")
    raw = "&".join(parts)
    digest = hmac.new(API_SECRET.encode(), raw.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()

def duration_ms(path):
    audio = AudioFile(str(path))
    if audio is None or audio.info is None:
        raise ValueError("无法读取音频时长或格式不受支持")
    return int(audio.info.length * 1000)

def upload(path):
    size = path.stat().st_size
    if size > 500 * 1024 * 1024:
        raise ValueError("文件超过500MB")
    params = {
        "appId": APP_ID,
        "accessKeyId": API_KEY,
        "dateTime": now_string(),
        "signatureRandom": ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16)),
        "fileSize": str(size),
        "fileName": path.name,
        "duration": str(duration_ms(path)),
        "language": "autodialect",
        "pd": "edu",
        "eng_smoothproc": str(SMOOTH).lower(),
        "eng_colloqproc": str(COLLOQUIAL).lower()
    }
    headers = {"Content-Type": "application/octet-stream", "signature": make_signature(params)}
    with path.open("rb") as f:
        r = requests.post(BASE_URL + "/v2/upload", params=params, headers=headers, data=f, timeout=(30, 600))
    r.raise_for_status()
    data = r.json()
    if str(data.get("code")) != "000000":
        raise RuntimeError(f"上传接口返回错误：{data}")
    order_id = data.get("content", {}).get("orderId")
    if not order_id:
        raise RuntimeError(f"上传结果缺少orderId：{data}")
    return order_id, params["signatureRandom"]

def get_result(order_id, random_value):
    start = time.time()
    while time.time() - start < MAX_WAIT_SECONDS:
        params = {
            "accessKeyId": API_KEY,
            "dateTime": now_string(),
            "signatureRandom": random_value,
            "orderId": order_id,
            "resultType": "transfer"
        }
        headers = {"Content-Type": "application/json", "signature": make_signature(params)}
        r = requests.post(BASE_URL + "/v2/getResult", params=params, headers=headers, json={}, timeout=60)
        r.raise_for_status()
        data = r.json()
        if str(data.get("code")) != "000000":
            raise RuntimeError(f"查询接口返回错误：{data}")
        content = data.get("content", {})
        info = content.get("orderInfo", {})
        status = info.get("status")
        print("    任务状态：", status)
        if str(status) == "4":
            if str(info.get("failType", 0)) not in ("0", "None", ""):
                raise RuntimeError(f"转写失败：{data}")
            return content.get("orderResult", "")
        if str(status) == "5":
            raise RuntimeError(f"任务失败：{data}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError("等待转写结果超时")

def extract_text(order_result):
    data = json.loads(order_result) if isinstance(order_result, str) else order_result
    words = []
    for item in data.get("lattice", []):
        raw = item.get("json_1best")
        if not raw:
            continue
        one = json.loads(raw) if isinstance(raw, str) else raw
        for rt in one.get("st", {}).get("rt", []):
            for ws in rt.get("ws", []):
                candidates = ws.get("cw", [])
                if candidates:
                    words.append(candidates[0].get("w", ""))
    text = "".join(words).strip()
    if not text:
        raise ValueError("未能从返回结果中提取文字，请检查讯飞返回格式")
    return text

def main():
    missing = [k for k, v in {"XF_APP_ID": APP_ID, "XF_API_KEY": API_KEY, "XF_API_SECRET": API_SECRET}.items() if not v]
    if missing:
        raise RuntimeError("请检查项目目录下的.env文件，缺少：" + ", ".join(missing))
    if not AUDIO_DIR.exists():
        raise FileNotFoundError(f"找不到录音文件夹：{AUDIO_DIR}")
    files = sorted(p for p in AUDIO_DIR.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS)
    if not files:
        print("class 5 文件夹中没有找到支持的音频文件")
        return
    print(f"找到 {len(files)} 个音频文件")
    rows = []
    for i, path in enumerate(files, 1):
        print(f"\\n[{i}/{len(files)}] {path.name}")
        try:
            order_id, rand = upload(path)
            print("    上传成功，订单号：", order_id)
            result = get_result(order_id, rand)
            transcript = extract_text(result)
            (OUTPUT_DIR / f"{path.stem}_转写.txt").write_text(transcript, encoding="utf-8-sig")
            print(f"    完成：{len(transcript)}字")
            rows.append({"文件名": path.name, "状态": "成功", "字数": len(transcript), "订单号": order_id, "错误": ""})
        except Exception as e:
            print("    失败：", e)
            rows.append({"文件名": path.name, "状态": "失败", "字数": 0, "订单号": "", "错误": str(e)})
    with (OUTPUT_DIR / "批量转写记录.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["文件名", "状态", "字数", "订单号", "错误"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\\n处理结束：成功 {sum(x['状态']=='成功' for x in rows)} / {len(files)}")
    print("结果保存在：", OUTPUT_DIR)

if __name__ == "__main__":
    main()
