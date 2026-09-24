#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaomi MiMo PWA 语法与自动化防卡死测试套件 (Frontend & Template Syntax Test Suite)
确保前端所有 JavaScript 脚本解析 100% 零 SyntaxError，防止白屏与“正在载入...”卡死复发。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server


class TestPwaSyntaxAndGuards(unittest.TestCase):
    """测试 PWA 模板的 JavaScript 语法完整性与安全防卡死机制"""

    def setUp(self):
        self.html = server.XIAOMI_MIMO_PWA_HTML
        self.scripts = re.findall(r"<script.*?>([\s\S]*?)</script>", self.html)

    def test_scripts_exist(self):
        """确保 HTML 中包含必要的脚本块"""
        self.assertGreaterEqual(len(self.scripts), 2, "HTML 模板中应当至少包含 2 个 script 标签")

    def test_node_check_all_scripts(self):
        """使用 node --check 对所有内嵌 script 进行严格的 JavaScript 语法检查"""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("未在系统 PATH 中找到 node 命令，跳过 node --check 校验")

        for idx, src in enumerate(self.scripts):
            clean_src = src.strip()
            if not clean_src:
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=True, encoding="utf-8") as tf:
                tf.write(clean_src)
                tf.flush()
                res = subprocess.run(
                    [node_bin, "--check", tf.name],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    res.returncode,
                    0,
                    f"第 {idx} 个 <script> 存在 JavaScript 语法错误:\n{res.stderr}",
                )

    def test_init_app_is_async(self):
        """必须声明为 async function initApp，以支持内部 await fetch 操作"""
        self.assertIn("async function initApp()", self.html, "initApp 必须声明为 async 函数")

    def test_error_boundary_present(self):
        """页面 head 中必须注册全局 error 监听兜底，防止出现任何异常时用户卡死在无响应页面"""
        self.assertIn("window.addEventListener('error'", self.html)
        self.assertIn("PWA Boot Guard", self.html)

    def test_safety_timeout_present(self):
        """必须包含安全超时解除机制（safetyTimer），防止后端通信异常时卡死在'正在载入...'"""
        self.assertIn("safetyTimer", self.html)
        self.assertIn("topTitle.textContent = \"当前任务\"", self.html)

    def test_server_validate_pwa_assets_runs(self):
        """调用服务自检函数 validate_pwa_assets() 必须无异常抛出"""
        try:
            server.validate_pwa_assets()
        except Exception as e:
            self.fail(f"validate_pwa_assets() 校验失败: {e}")


if __name__ == "__main__":
    unittest.main()
