"""
trim_pdf.py — 裁剪孤立 TOC 的 PDF

问题：CANN Ascend C 算子开发指南 技术部分 01.pdf
  - 物理页 4-11  : 第1-5章目录（与正文对应）
  - 物理页 12-54 : 第6章 API 参考目录（正文不在此PDF，43页孤立条目）
  - 物理页 55-755: 第1-5章正文
  - 物理页 756   : 第6章正文第1页（残缺，内容继续在别的PDF）

裁剪策略：只保留 p1-11 + p55-755，输出到同目录下加 _trimmed 后缀。

用法：
  python trim_pdf.py <input.pdf> [output.pdf]
"""
import sys
from pathlib import Path
import fitz  # PyMuPDF


def trim(input_path: str, output_path: str | None = None) -> Path:
    src = Path(input_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"PDF not found: {src}")

    dst = Path(output_path) if output_path else src.with_stem(src.stem + "_trimmed")

    doc = fitz.open(str(src))
    total = doc.page_count
    print(f"原始 PDF : {src.name}")
    print(f"物理页数 : {total}")

    # 保留的物理页范围（0-indexed）
    # p1-11  → index 0-10  : 封面+版权+安全声明+第1-5章目录
    # p55-755→ index 54-754: 第1-5章正文
    keep_ranges = [(0, 10), (54, 754)]
    keep_pages = []
    for lo, hi in keep_ranges:
        keep_pages.extend(range(lo, hi + 1))

    print(f"保留页面 : p1-11 ({10-0+1}页) + p55-755 ({754-54+1}页) = {len(keep_pages)} 页")
    print(f"丢弃页面 : p12-54（第6章孤立目录, 43页）+ p756（第6章残缺首页, 1页）")
    print()

    out_doc = fitz.open()
    out_doc.insert_pdf(doc, from_page=0, to_page=10)    # p1-11
    out_doc.insert_pdf(doc, from_page=54, to_page=754)  # p55-755
    out_doc.save(str(dst))
    out_doc.close()
    doc.close()

    size_mb = dst.stat().st_size / 1024 / 1024
    print(f"输出 PDF : {dst.name}")
    print(f"输出页数 : {len(keep_pages)} 页")
    print(f"输出大小 : {size_mb:.1f} MB")
    return dst


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python trim_pdf.py <input.pdf> [output.pdf]")
        sys.exit(1)
    output = sys.argv[2] if len(sys.argv) > 2 else None
    trim(sys.argv[1], output)
