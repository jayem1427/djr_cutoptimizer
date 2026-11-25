"""Render the command icons in commands/optimizer/resources/ from the SVGs in resources/src/.

small.svg is drawn for 16 px (simplified, per Fusion's icon guidance); large.svg for 32 px and up.
Needs Playwright with Chromium:  python tools/render_icons.py
"""
import pathlib
from playwright.sync_api import sync_playwright

RES = pathlib.Path(__file__).resolve().parent.parent / 'commands' / 'optimizer' / 'resources'
JOBS = [('small.svg', '16x16.png', 16), ('small.svg', '16x16@2x.png', 32),
        ('large.svg', '32x32.png', 32), ('large.svg', '32x32@2x.png', 64), ('large.svg', '64x64.png', 64)]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    for src, out, px in JOBS:
        svg = (RES / 'src' / src).read_text()
        page.set_viewport_size({'width': px, 'height': px})
        page.set_content(f'<style>html,body{{margin:0;background:transparent}}svg{{display:block;width:{px}px;height:{px}px}}</style>{svg}')
        page.screenshot(path=str(RES / out), omit_background=True, clip={'x': 0, 'y': 0, 'width': px, 'height': px})
        print('wrote', out)
    browser.close()
