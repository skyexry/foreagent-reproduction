"""检查 SiliconFlow API；--save-key 将密钥保存到个人配置目录。"""

import argparse
import getpass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-key", action="store_true", help="保存密钥后退出，不调用 API")
    args = parser.parse_args()
    key_path = Path.home() / ".config" / "foreagent" / "siliconflow.key"
    if args.save_key:
        api_key = getpass.getpass("请输入要保存的 API Key（输入不显示）：").strip()
        if not api_key:
            raise SystemExit("未输入密钥，未保存。")
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(api_key + "\n")
        print("密钥已保存，仅当前用户可读写。未调用 API。")
        return
    api_key = key_path.read_text().strip() if key_path.exists() else getpass.getpass("请输入 SiliconFlow API Key（输入不显示）：").strip()
    if not api_key:
        raise SystemExit("未输入密钥，已退出。")

    payload = {
        "model": "Pro/deepseek-ai/DeepSeek-V3.2",
        "messages": [{"role": "user", "content": "计算 17 × 23，并简短回答。"}],
        "enable_thinking": True,
        "thinking_budget": 1024,
        "max_tokens": 256,
        "stream": False,
    }
    request = urllib.request.Request(
        "https://api.siliconflow.cn/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        hints = {401: "请检查密钥。", 402: "请检查余额。", 403: "请检查模型权限。", 429: "触发限流，请稍后重试。"}
        raise SystemExit(f"请求失败：HTTP {exc.code}。{hints.get(exc.code, '请检查平台模型可用性和请求设置。')}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(f"网络连接失败：{exc.reason}") from None

    choice = result["choices"][0]
    message = choice["message"]
    print("返回模型：", result.get("model", "未提供"))
    print("是否返回思考内容：", bool(message.get("reasoning_content")))
    print("最终回答：", message.get("content"))
    print("结束原因：", choice.get("finish_reason"))
    print("Token 用量：", json.dumps(result.get("usage", {}), ensure_ascii=False))
    print("注意：本次仅验证接口，参数不作为正式复现实验设置。")


if __name__ == "__main__":
    main()
