释放文件：
python install_ai_dev_kit.py C:\Users\234393\ai-dev-kit

安装到copilot   先预演，再正式安装
cd /d C:\Users\234393\ai-dev-kit && python tools\install.py --dry-run


体检，自测，评估
python tools\kit_doctor.py & python tools\selftest.py & python tools\run_evals.py

# 5件事
1. 填 bat 路径：打开 kit.config.json，把 profiles.quota.launcher 改成公司 bat 的完整路径。
2. 看 bat 最后一行有没有 %*：有就把 agent_flag 改成 true，挂件能直接带 --agent 启动。
3. 两个版本各测一次拦截：会话里说“读一下 .env”，应该被 ai-dev-kit 拒绝。1.0.75 没被拦就重装：install.py --hook-style powershell。
4. 核对风格卡片：第一次在 tap-ai-backend 用之前，让 Copilot 用 /kit-extract-pattern 对照代码核对 8 张卡片（现在都标着“待核对”）。
5. 出问题时紧急关闭钩子：python tools\install.py --no-hooks。