# -*- coding: utf-8 -*-
"""
把交付页“复制全部文件”得到的打包文本还原成目录结构。

用法：
  1. 在交付页点“复制打包文本”，粘贴保存为 bundle.txt（UTF-8）
  2. python unpack_bundle.py bundle.txt 输出目录
只用 Python 标准库。
"""
import os
import sys

MARK = "===== FILE: "
END = " ====="


def main():
    if len(sys.argv) < 3:
        print("用法：python unpack_bundle.py bundle.txt 输出目录")
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        lines = f.read().replace("\r\n", "\n").split("\n")
    path, buf, count = None, [], 0

    def flush():
        nonlocal count
        if path is None:
            return
        target = os.path.normpath(os.path.join(out, path))
        if not target.startswith(os.path.normpath(out)):
            raise SystemExit("路径不合法：%s" % path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        text = "\n".join(buf)
        with open(target, "w", encoding="utf-8", newline="\n") as w:
            w.write(text.rstrip("\n") + "\n")
        count += 1
        print("  写入 " + path)

    for line in lines:
        if line.startswith(MARK) and line.endswith(END):
            flush()
            path, buf = line[len(MARK):-len(END)].strip(), []
        elif path is not None:
            buf.append(line)
    flush()
    print("完成：共还原 %d 个文件到 %s" % (count, out))


if __name__ == "__main__":
    main()
