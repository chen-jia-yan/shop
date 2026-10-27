先别改测试，按下面执行：
1. 贴出失败测试中 other.pdf（预置的已有文档）和 same-other.pdf（上传的文件）各自的内容字节，以及预置文档的 content_sha256 是怎么写的
2. 判断属于哪种情况：
   a. 预置文档的 content_sha256 是手写的假值，和上传内容的真实哈希不同 → 改为 hashlib.sha256(相同的内容).hexdigest()，断言不变（仍然是 skipped "与 other.pdf 内容相同"）
   b. 两边内容和哈希本来就一致，仍然判成新文件 → 这是 service 的 bug，停下来贴出 upload 中调用 find_by_sha 和组装 by_sha 的代码，不要改测试
3. 关于 repo factory：贴出 KbAdminService.__init__ 的完整签名，并确认：
   - 这个参数是可选的，默认使用真实的 KbDocumentRepo、KbJobRepo
   - 业务代码中没有"测试时走另一条路"的判断
   在完成报告的"偏离说明"中写明这一处
4. 全部测试通过后，再出完整的《完成报告》