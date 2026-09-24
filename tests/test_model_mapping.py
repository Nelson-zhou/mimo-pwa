#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaomi MiMo PWA 模型映射与会话感知自动化测试套件 (Model Mapping & Session Model Test Suite)
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import server


class TestModelMapping(unittest.TestCase):
    """测试多维模型注册表、别名归一化与会话级感知逻辑"""

    def test_resolve_canonical_official_models(self):
        """测试官方自研模型的别名归一化映射"""
        # Pro 系列
        self.assertEqual(server.resolve_canonical_model("mimo-pro"), "mimo-v2.6-pro")
        self.assertEqual(server.resolve_canonical_model("mimo-x-pro-preview"), "mimo-v2.6-pro")
        self.assertEqual(server.resolve_canonical_model("xiaomi/mimo-v2.6-pro"), "mimo-v2.6-pro")
        self.assertEqual(server.resolve_canonical_model("mimo/mimo-x-pro-preview"), "mimo-v2.6-pro")
        self.assertEqual(server.resolve_canonical_model("mimo-v2.6-pro"), "mimo-v2.6-pro")

        # Flash 系列
        self.assertEqual(server.resolve_canonical_model("mimo-flash"), "mimo-v2.6-flash")
        self.assertEqual(server.resolve_canonical_model("mimo-x-flash-preview"), "mimo-v2.6-flash")
        self.assertEqual(server.resolve_canonical_model("xiaomi/mimo-v2.6-flash"), "mimo-v2.6-flash")
        self.assertEqual(server.resolve_canonical_model("mimo-v2.6-flash"), "mimo-v2.6-flash")

        # Auto 系列
        self.assertEqual(server.resolve_canonical_model("mimo-auto"), "mimo-auto")
        self.assertEqual(server.resolve_canonical_model("mimo/mimo-auto"), "mimo-auto")
        self.assertEqual(server.resolve_canonical_model("xiaomi/mimo-auto"), "mimo-auto")
        self.assertEqual(server.resolve_canonical_model(None), "mimo-auto")
        self.assertEqual(server.resolve_canonical_model(""), "mimo-auto")

    def test_resolve_canonical_extended_models(self):
        """测试已配置拓展模型的别名归一化映射"""
        self.assertEqual(server.resolve_canonical_model("claude-sonnet-4-6"), "claude-sonnet-4-6")
        self.assertEqual(server.resolve_canonical_model("anthropic/claude-sonnet-4-6"), "claude-sonnet-4-6")
        self.assertEqual(server.resolve_canonical_model("deepseek-v4-pro"), "deepseek-v4-pro")
        self.assertEqual(server.resolve_canonical_model("anthropic/deepseek-v4-pro"), "deepseek-v4-pro")

    def test_get_model_info_structure(self):
        """测试模型元数据结构的完整性"""
        for mid in ["mimo-v2.6-pro", "mimo-v2.6-flash", "mimo-auto", "claude-sonnet-4-6"]:
            info = server.get_model_info(mid)
            self.assertIn("canonicalId", info)
            self.assertIn("name", info)
            self.assertIn("category", info)
            self.assertIn("badge", info)
            self.assertIn("contextWindow", info)
            self.assertIn("ratio", info)
            self.assertIn("desc", info)
            self.assertIn("capabilities", info)
            self.assertIsInstance(info["capabilities"], list)

    def test_get_available_models_list(self):
        """测试获取可用模型列表"""
        models = server.get_available_models()
        self.assertGreaterEqual(len(models), 3)
        canon_ids = [m["canonicalId"] for m in models]
        self.assertIn("mimo-auto", canon_ids)
        self.assertIn("mimo-v2.6-pro", canon_ids)
        self.assertIn("mimo-v2.6-flash", canon_ids)

    def test_get_session_model_resolution(self):
        """测试真实会话的模型解析"""
        act_id = server.get_desktop_current_session_id()
        if act_id:
            m = server.get_session_model(act_id)
            self.assertIsNotNone(m)
            self.assertIn("canonicalId", m)
            self.assertIn("name", m)

    def test_get_model_context_limit(self):
        """测试模型上下文尺寸计算"""
        self.assertEqual(server.get_model_context_limit("mimo-v2.6-pro"), 1_000_000)
        self.assertEqual(server.get_model_context_limit("mimo-v2.6-flash"), 1_000_000)
        self.assertEqual(server.get_model_context_limit("claude-sonnet-4-6"), 1_000_000)


if __name__ == "__main__":
    unittest.main()
