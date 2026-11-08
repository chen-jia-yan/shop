#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
秋芝餐厅品牌物料生成脚本 - 硅基流动 tongyi-mai/z-image-turbo 版
依赖：pip install requests
"""

import argparse
import base64
import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# ---------- 解决 Windows 终端编码 ----------
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ==================== 硅基流动配置 ====================
API_KEY = os.environ.get("SILICONFLOW_API_KEY", "sk-fopfyvrscsuiilmhjymrbfjgiutyxtcayvienerxzykugycd")
API_URL = "https://api.siliconflow.cn/v1/images/generations"
MODEL = "tongyi-mai/z-image-turbo"
# ======================================================

BRAND_STYLE = """
秋芝餐厅品牌视觉要求：
- 主色调：薄荷绿 (#5DDEB5) + 白色
- IP形象：3D 薄荷绿卡通葫芦（大眼睛、微笑、白色条纹）
- 整体风格：年轻、潮流、有网感、清新时尚、健康轻食
- 视觉质感：3D 卡通与实拍结合，杂志感排版，高饱和度、高食欲、商业摄影级别
"""

MATERIAL_INFO = {
    "hat":     {"cn": "员工帽子",   "size": "1024x1024"},
    "tshirt":  {"cn": "员工T恤",    "size": "1024x1024"},
    "apron":   {"cn": "员工围裙",   "size": "1024x1024"},
    "poster":  {"cn": "宣传海报",   "size": "720x1280"},
    "menu":    {"cn": "菜单",       "size": "1024x1024"},
    "social":  {"cn": "社交媒体配图","size": "1024x1024"},
    "coupon":  {"cn": "优惠券",     "size": "1024x1024"},
    "box":     {"cn": "餐盒",       "size": "1024x1024"},
    "banner":  {"cn": "网站横幅",   "size": "1280x720"},
}


def build_prompt(requirement: str, material_type: str) -> str:
    info = MATERIAL_INFO[material_type]
    return f"""
{BRAND_STYLE}
请生成符合以上品牌风格的{info['cn']}图片。
具体场景需求：{requirement}
要求：
1. 构图必须包含3D薄荷绿卡通葫芦IP形象
2. 色彩严格遵循薄荷绿(#5DDEB5)和白色的搭配
3. 画面干净，不要有乱码文字
4. 适合商业使用的高清图片
""".strip()


def encode_ref_image(filepath: str) -> str:
    """本地参考图 -> base64 data URI"""
    path = Path(filepath)
    if not path.exists():
        raise Exception(f"参考图不存在：{filepath}")
    suffix = path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(suffix, "image/png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def generate_images(prompt: str, material_type: str, ref_img: str = None, num_images: int = 1):
    size = MATERIAL_INFO[material_type]["size"]
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "image_size": size,
        "batch_size": num_images,
        "num_inference_steps": 20,
        "guidance_scale": 7.5
    }
    if ref_img:
        payload["image"] = ref_img
        print(f"🖼️  已附加参考图")

    resp = requests.post(API_URL, headers=headers, json=payload)
    result = resp.json()

    if "images" not in result:
        raise Exception(f"生成失败：{result}")

    urls = [img["url"] for img in result["images"]]
    print(f"✅ 成功生成 {len(urls)} 张图片")
    return urls


def download_and_save(image_url: str, output_path: str, material_type: str, index: int = 0):
    output = Path(output_path)
    if output.suffix == '' or output.is_dir():
        output.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"qiuzhi_{material_type}_{ts}_{index+1}.png"
        output = output / fname
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    print(f"📥 正在下载第{index+1}张...")
    img_resp = requests.get(image_url, timeout=30)
    img_resp.raise_for_status()

    with open(output, 'wb') as f:
        f.write(img_resp.content)

    print(f"✅ 保存成功：{output.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="秋芝餐厅物料生成器-硅基流动版")
    parser.add_argument("requirement", help="具体需求描述")
    parser.add_argument("-t", "--type", required=True,
                        choices=list(MATERIAL_INFO.keys()),
                        help="物料类型")
    parser.add_argument("-o", "--output", default="./output",
                        help="输出路径")
    parser.add_argument("-r", "--ref", default=None,
                        help="参考图路径（如 logo.png）")
    parser.add_argument("-n", "--num", type=int, default=1,
                        help="生成张数（默认1张）")

    args = parser.parse_args()

    if len(API_KEY) < 20:
        print("❌ 请先填入你的硅基流动 API_KEY")
        sys.exit(1)

    # 参考图
    ref_img = None
    if args.ref:
        print(f"🖼️  读取参考图：{args.ref}")
        ref_img = encode_ref_image(args.ref)

    # 拼装 prompt
    prompt = build_prompt(args.requirement, args.type)
    print("📝 已自动生成提示词")

    # 生成
    img_urls = generate_images(prompt, args.type, ref_img=ref_img, num_images=args.num)

    # 下载
    for i, url in enumerate(img_urls):
        download_and_save(url, args.output, args.type, index=i)


if __name__ == "__main__":
    main()