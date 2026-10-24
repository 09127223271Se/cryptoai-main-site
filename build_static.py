"""
build_static.py — renders the site into dist/ as plain static files (no Flask needed).
Used for the hosted preview: AI runs through Claude in the preview, the trader uses sample data/CSV.
    python build_static.py
"""
import os
import shutil
from jinja2 import Environment, FileSystemLoader

BASE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(BASE, "dist")
PAGES = {"home": ("brief.html", "index.html"), "radio": ("index.html", "radio.html"), "trader": ("trader.html", "trader.html"),
         "analysis": ("analysis.html", "analysis.html"), "sales": ("sales.html", "sales.html"), "admin": ("index.html", "index.html")}

env = Environment(loader=FileSystemLoader(os.path.join(BASE, "templates")), autoescape=True)
shutil.rmtree(DIST, ignore_errors=True)
shutil.copytree(os.path.join(BASE, "static"), os.path.join(DIST, "static"))
for name, (tpl, out) in [i for i in PAGES.items() if i[0] != "admin"]:
    html = env.get_template(tpl).render(
        page=name, mode="static", api_base="", is_admin=True, channel="",
        asset=lambda p: "static/" + p,
        link=lambda n: PAGES[n][1],
        fragment=(name == "home"),   # the preview host wraps the main page in its own <html>/<head>
    )
    with open(os.path.join(DIST, out), "w", encoding="utf-8") as f:
        f.write(html)
print("built", DIST)
