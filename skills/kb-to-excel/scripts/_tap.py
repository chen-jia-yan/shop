# -*- coding: utf-8 -*-
"""找到共享配置目录 tap-config 并按本 skill 的范围加载默认配置。"""
import os
import sys

SCOPE = "excel"


def _locate():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.environ.get("TAP_CONFIG_HOME"),
              os.path.join(here, "..", "..", "tap-config"),
              os.path.join(here, "..", "tap-config")):
        if d and os.path.isfile(os.path.join(d, "tapconf.py")):
            return os.path.abspath(d)
    sys.exit("找不到 tap-config 目录：请把它和各 skill 目录放在同一级，或设置环境变量 TAP_CONFIG_HOME")


sys.path.insert(0, _locate())
from tapconf import CONF, add_cli_args, configure  # noqa: E402,F401

if CONF.scope != SCOPE:
    CONF.load(SCOPE)
