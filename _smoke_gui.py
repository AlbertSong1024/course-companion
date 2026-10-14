# -*- coding: utf-8 -*-
"""快速冒烟：导入 GUI 入口并实例化 LoginApp（不联网、不开浏览器）。"""
import course_companion_gui
import course_companion_login as L
app = L.LoginApp({"account": "", "password": ""}, on_close=lambda: None)
print("LoginApp OK; title =", app.root.title())
app.root.destroy()
print("smoke OK")
