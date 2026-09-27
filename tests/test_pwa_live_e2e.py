import unittest
import urllib.request
import subprocess
import shutil
import re
import os

class TestPwaLiveE2E(unittest.TestCase):
    BASE_URL = "http://127.0.0.1:8081"

    def test_01_http_root_accessible(self):
        try:
            req = urllib.request.Request(self.BASE_URL, headers={"User-Agent": "Mozilla/5.0 (PWA Regression Test)"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8", errors="ignore")
                self.assertIn("Xiaomi MIMO", body)
                self.assertIn("id=\"chat-viewport\"", body)
        except Exception as e:
            self.fail(f"无法访问本地 PWA 服务 {self.BASE_URL}: {e}")

    def test_02_script_runtime_clean_evaluation(self):
        req = urllib.request.Request(self.BASE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.DOTALL)
        self.assertGreater(len(scripts), 0, "页面中必须存在内嵌脚本")

        harness = """
const window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    innerWidth: 375,
    innerHeight: 667,
    matchMedia: () => ({ matches: false }),
    location: { reload: () => {}, search: "", protocol: "http:", hostname: "127.0.0.1" },
    navigator: { vibrate: () => {}, userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)" }
};
const location = window.location;
const navigator = window.navigator;
const document = {
    getElementById: (id) => ({
        classList: { add: ()=>{}, remove: ()=>{}, contains: ()=>false, toggle: ()=>{} },
        style: {},
        appendChild: ()=>{},
        addEventListener: ()=>{},
        setAttribute: ()=>{},
        value: "",
        innerHTML: "",
        textContent: ""
    }),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
    createElement: () => ({ style: {}, classList: { add: ()=>{} } }),
    body: { appendChild: ()=>{} }
};
const fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
const setInterval = () => 0;
const setTimeout = (fn) => 0;
const EventSource = function() {
    return { addEventListener: () => {}, onerror: () => {}, close: () => {} };
};
"""
        main_script = scripts[-1]
        runner_code = harness + "\n" + main_script

        res = subprocess.run(
            ["node"],
            input=runner_code,
            capture_output=True,
            text=True,
            timeout=5
        )
        self.assertEqual(res.returncode, 0, f"客户端脚本在模拟执行中发生运行时异常: {res.stderr}")

    def test_03_headless_chrome_render(self):
        chrome_bin = shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium")
        if not chrome_bin:
            self.skipTest("系统未安装 Chrome/Chromium，跳过真实无头浏览器渲染测试")

        res = subprocess.run(
            [chrome_bin, "--headless=new", "--disable-gpu", "--dump-dom", self.BASE_URL],
            capture_output=True,
            text=True,
            timeout=10
        )
        self.assertEqual(res.returncode, 0, f"无头 Chrome 渲染失败: {res.stderr}")
        dom = res.stdout

        # 剥离所有 <script> 标签后再检查渲染生成的 DOM 元素内容
        visible_dom = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", dom, flags=re.DOTALL)
        self.assertNotIn("⚠️ 界面加载遇到异常", visible_dom, "页面触发了错误拦截兜底（Error Boundary）")
        self.assertNotIn("运行异常", visible_dom, "页面顶栏标题显示为运行异常")
        self.assertNotIn("Uncaught ReferenceError", visible_dom)
        self.assertNotIn("Uncaught TypeError", visible_dom)

        self.assertIn("<header>", dom, "未找到顶部导航条")
        self.assertIn("id=\"top-session-title\"", dom, "未找到标题容器")
        self.assertIn("id=\"chat-viewport\"", dom, "未找到对话主视口")
        self.assertIn("id=\"dock-input\"", dom, "未找到底栏输入区")
        self.assertIn("id=\"model-sheet\"", dom, "未找到移动端模型选择抽屉")

if __name__ == "__main__":
    unittest.main()
