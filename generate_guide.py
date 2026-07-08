# -*- coding: utf-8 -*-
"""
生成自包含的 HTML 仪表盘页面：指标卡 + 分类概览 + 最近更新 + 目录树 + 全文搜索 + Markdown 渲染。
用法：python generate_guide.py
产出：导览.html （双击即可在浏览器打开，离线可用）
"""
import os
import re
import json
import time
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(ROOT, "导览.html")

# 忽略这些目录
IGNORE_DIRS = {".claude", ".obsidian", ".workbuddy", "__pycache__", ".git"}

NOW = time.time()
WEEK = 7 * 86400

# 顶级分类的友好别名（无别名则用目录名本身）
CATEGORY_ALIAS = {
    "设计": "🎨 设计",
    "商业计划书": "📊 商业计划",
}


def humanize_when(ts):
    """把时间戳渲染成相对时间文案。"""
    delta = NOW - ts
    if delta < 3600:
        m = max(1, int(delta // 60))
        return f"{m} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    d = int(delta // 86400)
    if d < 30:
        return f"{d} 天前"
    if d < 365:
        return f"{d // 30} 个月前"
    return f"{d // 365} 年前"


def collect_md():
    items = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            if not fn.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            try:
                with open(full, "r", encoding="utf-8") as f:
                    raw = f.read()
                mtime = int(os.path.getmtime(full))
            except Exception as e:
                raw = f"(读取失败: {e})"
                mtime = 0
            # 正文用于搜索（去掉 markdown 标记，降低体积/噪音）
            plain = re.sub(r"[#`*_>\-\[\]\(\)!|]", " ", raw)
            plain = re.sub(r"\s+", " ", plain).strip()
            # 提取首段作为简介
            intro = ""
            for ln in raw.splitlines():
                s = ln.strip().lstrip("#").strip()
                if s and not s.startswith(("!", "|", "```", "-")):
                    intro = s[:80]
                    break
            items.append({
                "path": rel,
                "name": fn[:-3],
                "content": raw,
                "plain": plain,
                "intro": intro,
                "mtime": mtime,
                "when": humanize_when(mtime),
            })
    items.sort(key=lambda x: x["path"])
    return items


def build_stats(items):
    """计算仪表盘需要的聚合数据。"""
    total = len(items)
    # 顶级分类
    cat_counter = Counter()
    for it in items:
        top = it["path"].split("/")[0]
        cat_counter[top] += 1
    categories = [
        {"key": k, "name": CATEGORY_ALIAS.get(k, k), "count": c, "pct": round(c / total * 100) if total else 0}
        for k, c in cat_counter.most_common()
    ]
    # 方案库（计划库）数量
    plan_count = sum(1 for it in items if "02_计划库" in it["path"] or "02_方案库" in it["path"])
    # 产品库数量
    product_count = sum(1 for it in items if "01_产品库" in it["path"])
    # 本周更新
    week_count = sum(1 for it in items if it["mtime"] and (NOW - it["mtime"]) <= WEEK)
    # 最近更新（按修改时间倒序，取前 8）
    recent = sorted(
        [it for it in items if it["mtime"]],
        key=lambda x: x["mtime"], reverse=True
    )[:8]
    recent_brief = [{"path": r["path"], "name": r["name"], "when": r["when"], "intro": r["intro"]} for r in recent]
    return {
        "total": total,
        "categories": categories,
        "planCount": plan_count,
        "productCount": product_count,
        "weekCount": week_count,
        "recent": recent_brief,
    }


def build_tree(items):
    """构建嵌套目录树。"""
    root = {"name": "root", "children": {}, "files": []}
    for it in items:
        parts = it["path"].split("/")
        node = root
        for p in parts[:-1]:
            node = node["children"].setdefault(p, {"name": p, "children": {}, "files": []})
        node["files"].append(it)
    return root


def render_tree(node, depth=0):
    """把目录树渲染成 HTML（递归）。"""
    html = []
    for name in sorted(node["children"].keys()):
        child = node["children"][name]
        sub = render_tree(child, depth + 1)
        html.append(
            f'<details class="dir" open>'
            f'<summary><span class="dir-icon">📁</span>{name}</summary>'
            f'<div class="dir-body">{sub}</div></details>'
        )
    for f in node["files"]:
        html.append(
            f'<a class="file" data-path="{f["path"]}" href="#'
            + f["path"]
            + f'"><span class="file-icon">📄</span>{f["name"]}</a>'
        )
    return "".join(html)


# 轻量 Markdown 渲染器（vanilla JS 注入到前端）
RENDERER_JS = r"""
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function inline(s){
  s=escapeHtml(s);
  s=s.replace(/\[\[([^\]]+)\]\]/g,function(m,inner){return wikiLink(inner);});
  s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s=s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g,'<img alt="$1" src="$2" />');
  s=s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
  s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  s=s.replace(/__([^_]+)__/g,'<strong>$1</strong>');
  s=s.replace(/\*([^*]+)\*/g,'<em>$1</em>');
  s=s.replace(/~~([^~]+)~~/g,'<del>$1</del>');
  return s;
}
function renderMarkdown(md){
  const lines=md.split(/\r?\n/);
  let out=[],i=0,inCode=false,codeBuf=[],listType=null;
  const closeList=()=>{if(listType){out.push(`</${listType}>`);listType=null;}};
  while(i<lines.length){
    let line=lines[i];
    if(/^```/.test(line)){
      if(!inCode){closeList();inCode=true;codeBuf=[];}
      else{out.push('<pre><code>'+escapeHtml(codeBuf.join('\n'))+'</code></pre>');inCode=false;}
      i++;continue;
    }
    if(inCode){codeBuf.push(line);i++;continue;}
    if(!line.trim()){closeList();i++;continue;}
    let hm=/^(#{1,6})\s+(.*)$/.exec(line);
    if(hm){closeList();const lv=hm[1].length;out.push(`<h${lv}>${inline(hm[2])}</h${lv}>`);i++;continue;}
    if(/^(\*\*\*|---|___)\s*$/.test(line)){closeList();out.push('<hr/>');i++;continue;}
    if(/^>\s?/.test(line)){closeList();out.push('<blockquote>'+inline(line.replace(/^>\s?/,''))+'</blockquote>');i++;continue;}
    if(/\|/.test(line) && i+1<lines.length && /^\|?\s*:?-+/.test(lines[i+1])){
      closeList();
      const header=line.split('|').map(x=>x.trim()).filter(Boolean);
      i+=2;const rows=[];
      while(i<lines.length && /\|/.test(lines[i])){rows.push(lines[i].split('|').map(x=>x.trim()).filter(Boolean));i++;}
      let t='<table><thead><tr>'+header.map(c=>`<th>${inline(c)}</th>`).join('')+'</tr></thead><tbody>';
      rows.forEach(r=>{t+='<tr>'+r.map(c=>`<td>${inline(c)}</td>`).join('')+'</tr>';});
      t+='</tbody></table>';out.push(t);continue;
    }
    if(/^\s*([-*+])\s+/.test(line)){
      if(listType!=='ul'){closeList();out.push('<ul>');listType='ul';}
      out.push('<li>'+inline(line.replace(/^\s*([-*+])\s+/,''))+'</li>');i++;continue;
    }
    if(/^\s*\d+\.\s+/.test(line)){
      if(listType!=='ol'){closeList();out.push('<ol>');listType='ol';}
      out.push('<li>'+inline(line.replace(/^\s*\d+\.\s+/,''))+'</li>');i++;continue;
    }
    closeList();
    let buf=[line];
    while(i+1<lines.length && lines[i+1].trim() && !/^(#{1,6}\s|>|```|\s*([-*+])\s|\s*\d+\.\s|\*\*\*|---|___)/.test(lines[i+1]) && !/\|/.test(lines[i+1])){
      i++;buf.push(lines[i]);
    }
    out.push('<p>'+inline(buf.join(' '))+'</p>');i++;
  }
  if(inCode)out.push('<pre><code>'+escapeHtml(codeBuf.join('\n'))+'</code></pre>');
  closeList();
  return out.join('\n');
}
"""


def build_html(items, tree_html, stats):
    data_json = json.dumps(items, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>手工文创 · 笔记仪表盘</title>
<style>
:root{{
  --bg:#f5efe6;--bg-2:#ece2d3;--panel:#ffffff;--panel-2:#fbf6ef;
  --ink:#33291f;--ink-soft:#6a5d50;--muted:#a29589;
  --accent:#a86530;--accent-hi:#bd7a42;--accent-soft:#f1e1cb;
  --line:#e8ddcd;--line-soft:#f2ebdf;--hover:#f7efe1;
  --code-bg:#f5ecdf;--th-bg:#f3e9d9;--pre-bg:#2c241d;--pre-ink:#f3ede4;--mark:#ffd97a;
  --shadow-xs:0 1px 2px rgba(108,80,45,.05);
  --shadow-sm:0 2px 10px rgba(108,80,45,.07);
  --shadow-md:0 8px 24px rgba(108,80,45,.1);
  --shadow-lg:0 14px 36px rgba(108,80,45,.13);
  --radius:14px;--radius-lg:20px;
  --grad-brand:linear-gradient(135deg,#a86530 0%,#cd9054 100%);
  --grad-sage:#e7efe1;--c-sage:#6f9466;
  --grad-rose:#f6e4df;--c-rose:#bf6f60;
  --grad-blue:#e4e9f3;--c-blue:#6b7ba8;
}}
*{{box-sizing:border-box;}}
html,body{{margin:0;height:100%;}}
body{{
  font-family:"PingFang SC","Microsoft YaHei",-apple-system,Segoe UI,Roboto,sans-serif;
  background:radial-gradient(1200px 600px at 100% 0%,var(--bg-2),var(--bg)) fixed;
  color:var(--ink);display:flex;flex-direction:column;height:100vh;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
}}
::-webkit-scrollbar{{width:10px;height:10px;}}
::-webkit-scrollbar-track{{background:transparent;}}
::-webkit-scrollbar-thumb{{background:var(--line);border-radius:6px;border:2px solid transparent;background-clip:padding-box;}}
::-webkit-scrollbar-thumb:hover{{background:var(--muted);background-clip:padding-box;}}

/* ===== 顶栏 ===== */
header{{
  display:flex;align-items:center;gap:14px;padding:14px 22px;
  background:linear-gradient(90deg,var(--panel),var(--panel-2));
  border-bottom:1px solid var(--line);box-shadow:var(--shadow-sm);flex-shrink:0;z-index:5;
}}
header h1{{
  font-size:18px;margin:0;font-weight:700;background:var(--grad-brand);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px;
}}
header .sub{{font-size:12px;color:var(--muted);margin-top:2px;}}
.search-wrap{{flex:1;max-width:560px;position:relative;margin-left:auto;}}
#search{{
  width:100%;padding:10px 16px 10px 38px;border:1px solid var(--line);border-radius:24px;
  font-size:14px;background:var(--bg);outline:none;transition:.2s;color:var(--ink);
}}
#search:focus{{border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-soft);background:var(--panel);}}
.search-wrap::before{{content:"🔍";position:absolute;left:13px;top:50%;transform:translateY(-50%);font-size:14px;opacity:.55;}}
.icon-btn{{
  border:1px solid var(--line);background:var(--panel);cursor:pointer;
  font-size:15px;line-height:1;display:flex;align-items:center;justify-content:center;
  transition:.2s;flex-shrink:0;width:38px;height:38px;border-radius:50%;box-shadow:var(--shadow-xs);
}}
.icon-btn:hover{{border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-soft);transform:translateY(-1px);}}
.count-badge{{
  font-size:12px;color:var(--accent);background:var(--accent-soft);padding:6px 14px;
  border-radius:14px;white-space:nowrap;font-weight:500;
}}

/* ===== 侧栏 ===== */
.layout{{flex:1;display:flex;overflow:hidden;}}
aside{{
  width:300px;flex-shrink:0;background:var(--panel);border-right:1px solid var(--line);
  overflow-y:auto;padding:12px 10px;
}}
aside details.dir{{margin:3px 0;}}
aside summary{{
  cursor:pointer;list-style:none;padding:6px 10px;border-radius:8px;font-size:13px;
  font-weight:600;color:var(--ink-soft);user-select:none;transition:.15s;
}}
aside summary::-webkit-details-marker{{display:none;}}
aside summary:hover{{background:var(--hover);color:var(--accent);}}
.dir-icon{{margin-right:7px;}}
.dir-body{{padding-left:14px;border-left:1px dashed var(--line);margin:3px 0 3px 9px;}}
a.file{{
  display:flex;align-items:center;gap:7px;padding:6px 11px;border-radius:8px;
  font-size:13px;color:var(--ink-soft);text-decoration:none;cursor:pointer;transition:.15s;
}}
a.file:hover{{background:var(--hover);color:var(--accent);}}
a.file.active{{background:var(--accent-soft);color:var(--accent);font-weight:600;}}
.file-icon{{opacity:.6;font-size:12px;}}

.filter-chip{{
  display:none;align-items:center;gap:6px;margin:0 6px 10px;padding:6px 12px;
  background:var(--accent-soft);border:1px solid var(--accent);border-radius:14px;font-size:12px;
  color:var(--accent);cursor:pointer;font-weight:500;user-select:none;
}}
.filter-chip.show{{display:inline-flex;}}

.recent-wrap{{padding:4px 6px 10px;margin-bottom:8px;border-bottom:1px solid var(--line-soft);}}
.recent-head{{font-size:11px;color:var(--muted);letter-spacing:1.5px;margin:4px 6px 8px;font-weight:600;}}
.recent-list{{display:flex;flex-direction:column;gap:2px;}}
.recent-list a{{
  font-size:13px;padding:6px 9px;border-radius:7px;cursor:pointer;text-decoration:none;
  color:var(--ink-soft);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:.15s;
}}
.recent-list a:hover{{background:var(--hover);color:var(--accent);}}
.recent-list .clear{{color:var(--muted);font-size:11px;text-align:right;padding:6px 9px;cursor:pointer;}}
.recent-list .clear:hover{{color:var(--accent);}}

/* ===== 主区 / 仪表盘 ===== */
main{{flex:1;overflow-y:auto;padding:32px 40px;}}
.content-wrap{{max-width:1000px;margin:0 auto;}}

.dash-hero{{
  background:var(--grad-brand);border-radius:var(--radius-lg);padding:26px 30px;margin-bottom:28px;
  color:#fff;display:flex;align-items:center;justify-content:space-between;gap:16px;
  box-shadow:var(--shadow-md);position:relative;overflow:hidden;
}}
.dash-hero::after{{content:"";position:absolute;right:-50px;top:-50px;width:220px;height:220px;
  background:radial-gradient(circle,rgba(255,255,255,.2),transparent 70%);}}
.dash-hero h2{{margin:0 0 6px;font-size:21px;font-weight:700;letter-spacing:1px;}}
.dash-hero p{{margin:0;font-size:13px;opacity:.92;line-height:1.6;}}
.dash-hero .hero-emoji{{font-size:44px;filter:drop-shadow(0 2px 6px rgba(0,0,0,.2));}}

.dash-section{{margin-bottom:32px;}}
.section-title{{font-size:12px;color:var(--muted);letter-spacing:2px;margin:0 0 14px;font-weight:600;
  display:flex;align-items:center;gap:8px;}}
.section-title::before{{content:"";width:3px;height:13px;background:var(--accent);border-radius:2px;}}

.stat-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;}}
.stat-card{{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:20px;
  box-shadow:var(--shadow-sm);position:relative;overflow:hidden;transition:.25s;
}}
.stat-card:hover{{transform:translateY(-3px);box-shadow:var(--shadow-lg);}}
.stat-card .ico{{
  width:42px;height:42px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  font-size:20px;margin-bottom:14px;
}}
.stat-card .num{{font-size:30px;font-weight:800;color:var(--ink);line-height:1;letter-spacing:-.5px;}}
.stat-card .lbl{{font-size:12px;color:var(--muted);margin-top:7px;font-weight:500;}}
.stat-card .bar{{position:absolute;left:0;top:0;bottom:0;width:4px;}}

.cat-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;}}
.cat-card{{
  background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;
  cursor:pointer;transition:.2s;display:flex;flex-direction:column;gap:10px;box-shadow:var(--shadow-xs);
}}
.cat-card:hover{{border-color:var(--accent);box-shadow:var(--shadow-md);transform:translateY(-2px);}}
.cat-card.active{{border-color:var(--accent);background:var(--accent-soft);}}
.cat-card .cat-top{{display:flex;align-items:center;justify-content:space-between;}}
.cat-card .cat-name{{font-size:14px;font-weight:600;color:var(--ink);}}
.cat-card .cat-count{{font-size:13px;color:var(--accent);font-weight:700;}}
.cat-card .cat-bar{{height:6px;background:var(--line-soft);border-radius:3px;overflow:hidden;}}
.cat-card .cat-bar i{{display:block;height:100%;background:var(--grad-brand);border-radius:3px;}}

.recent-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;}}
.recent-item{{
  background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:11px;padding:13px 15px;cursor:pointer;transition:.2s;display:flex;flex-direction:column;gap:5px;
  box-shadow:var(--shadow-xs);
}}
.recent-item:hover{{border-left-color:var(--accent-hi);box-shadow:var(--shadow-md);transform:translateX(2px);}}
.recent-item .ri-top{{display:flex;align-items:center;justify-content:space-between;gap:8px;}}
.recent-item .ri-name{{font-size:14px;font-weight:600;color:var(--accent);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.recent-item .ri-when{{font-size:11px;color:var(--muted);white-space:nowrap;flex-shrink:0;background:var(--line-soft);padding:2px 8px;border-radius:10px;}}
.recent-item .ri-intro{{font-size:12px;color:var(--ink-soft);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.recent-item .ri-path{{font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}

/* ===== 阅读器 ===== */
.reader{{
  max-width:860px;margin:0 auto;background:var(--panel);padding:42px 52px;
  border-radius:var(--radius-lg);border:1px solid var(--line);min-height:60vh;box-shadow:var(--shadow-sm);
}}
.back-link{{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--accent);
  cursor:pointer;margin:0 0 16px 4px;text-decoration:none;font-weight:500;transition:.15s;}}
.back-link:hover{{opacity:.75;gap:9px;}}
.reader h1,.reader h2,.reader h3{{color:#4a3f33;border-bottom:1px solid var(--line);padding-bottom:8px;}}
.reader h1{{font-size:26px;margin-top:0;}}
.reader h2{{font-size:21px;margin-top:32px;}}
.reader h3{{font-size:17px;}}
.reader p{{line-height:1.85;font-size:15px;color:var(--ink);}}
.reader a{{color:var(--accent);}}
.reader code{{background:var(--code-bg);padding:2px 6px;border-radius:4px;font-size:13px;font-family:Consolas,Monaco,monospace;}}
.reader pre{{background:var(--pre-bg);color:var(--pre-ink);padding:16px;border-radius:8px;overflow-x:auto;}}
.reader pre code{{background:none;color:inherit;padding:0;}}
.reader blockquote{{border-left:3px solid var(--accent);background:var(--accent-soft);margin:0 0 16px;padding:10px 16px;color:var(--ink-soft);border-radius:0 6px 6px 0;}}
.reader table{{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px;}}
.reader th,.reader td{{border:1px solid var(--line);padding:8px 12px;text-align:left;}}
.reader th{{background:var(--th-bg);font-weight:600;}}
.reader img{{max-width:100%;border-radius:8px;}}
.reader ul,.reader ol{{line-height:1.85;font-size:15px;padding-left:24px;}}
.breadcrumb{{font-size:12px;color:var(--muted);margin-bottom:16px;word-break:break-all;}}

/* 双链 */
.reader .wikilink{{color:var(--accent);text-decoration:none;border-bottom:1px dashed var(--accent);cursor:pointer;}}
.reader .wikilink:hover{{opacity:.7;}}
.reader .wikilink-missing{{color:var(--muted);border-bottom:1px dashed var(--muted);cursor:help;}}

/* 长文目录 */
.toc{{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-bottom:24px;}}
.toc-title{{font-size:12px;color:var(--muted);letter-spacing:1.5px;font-weight:600;margin-bottom:10px;}}
.toc-body{{display:flex;flex-direction:column;gap:1px;max-height:240px;overflow-y:auto;}}
a.toc-link{{font-size:13px;color:var(--ink-soft);text-decoration:none;padding:4px 8px;border-radius:6px;cursor:pointer;line-height:1.5;transition:.15s;}}
a.toc-link:hover{{background:var(--hover);color:var(--accent);}}
a.toc-link.toc-sub{{padding-left:24px;font-size:12.5px;}}

.search-results{{list-style:none;padding:0;margin:0;}}
.search-results li{{padding:11px;border-radius:9px;cursor:pointer;transition:.15s;}}
.search-results li:hover{{background:var(--hover);}}
.search-results .name{{font-weight:600;color:var(--accent);}}
.search-results .path{{font-size:11px;color:var(--muted);margin-bottom:4px;}}
.search-results .snippet{{font-size:13px;color:var(--ink-soft);line-height:1.6;}}
.search-results .hit-badge{{float:right;font-size:11px;color:var(--muted);background:var(--line-soft);padding:1px 8px;border-radius:10px;font-weight:500;}}

/* 上一篇 / 下一篇 */
.reader-nav{{display:flex;justify-content:space-between;gap:12px;margin-top:34px;padding-top:22px;border-top:1px solid var(--line);}}
a.nav-link{{display:flex;flex-direction:column;gap:3px;text-decoration:none;border:1px solid var(--line);border-radius:10px;padding:11px 14px;flex:1;max-width:48%;transition:.15s;}}
a.nav-link:hover{{border-color:var(--accent);background:var(--hover);}}
a.nav-link.next{{align-items:flex-end;text-align:right;}}
.nav-dir{{font-size:12px;color:var(--muted);}}
.nav-name{{font-size:13px;color:var(--accent);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}

/* 内容分布图 */
.chart{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow-xs);display:flex;flex-direction:column;gap:11px;}}
.chart-row{{display:flex;align-items:center;gap:12px;}}
.chart-label{{font-size:13px;color:var(--ink-soft);width:120px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.chart-track{{flex:1;height:18px;background:var(--line-soft);border-radius:9px;overflow:hidden;}}
.chart-track i{{display:block;height:100%;background:var(--grad-brand);border-radius:9px;transition:width .4s;}}
.chart-val{{font-size:13px;color:var(--accent);font-weight:700;width:34px;text-align:right;flex-shrink:0;}}

/* 移动端抽屉触发与遮罩（默认隐藏） */
.menu-btn{{display:none;}}
.scrim{{display:none;}}

/* 打印：单篇导出 PDF */
@media print{{
  header,aside,.scrim,.back-link,.count-badge,.icon-btn,.toc,.reader-nav,.search-wrap{{display:none!important;}}
  body{{background:#fff!important;height:auto;}}
  main{{overflow:visible!important;padding:0!important;}}
  .content-wrap{{max-width:none;}}
  .reader{{box-shadow:none!important;border:none!important;padding:0!important;max-width:none;}}
  .reader h1,.reader h2,.reader h3{{color:#000!important;}}
  a{{color:#000!important;text-decoration:none!important;}}
}}
.hidden{{display:none!important;}}

@media(max-width:900px){{
  .stat-grid{{grid-template-columns:repeat(2,1fr);}}
  .recent-grid{{grid-template-columns:1fr;}}
  .dash-hero{{flex-direction:column;text-align:center;}}
}}
@media(max-width:780px){{
  .menu-btn{{display:flex;}}
  .scrim{{display:block;position:fixed;inset:0;background:rgba(40,28,18,.35);z-index:15;opacity:0;pointer-events:none;transition:.25s;}}
  .scrim.show{{opacity:1;pointer-events:auto;}}
  #sidebar{{position:fixed;top:0;left:0;bottom:0;width:280px;transform:translateX(-100%);transition:transform .25s;z-index:20;box-shadow:var(--shadow-lg);}}
  #sidebar.open{{transform:translateX(0);}}
  .reader{{padding:24px;}}main{{padding:18px;}}
  .chart-label{{width:92px;}}
  a.nav-link{{max-width:none;}}
}}
</style>
</head>
<body>
<header>
  <div>
    <h1>🧵 手工文创 · 笔记仪表盘</h1>
    <div class="sub">共 <span id="sub-count"></span> 篇 · 仪表盘 / 目录 / 全文搜索</div>
  </div>
  <div class="search-wrap">
    <input id="search" type="search" placeholder="搜索文件名或正文内容…" autocomplete="off"/>
  </div>
  <button id="menu-btn" class="icon-btn menu-btn" title="目录" aria-label="打开目录">☰</button>
  <button id="home-btn" class="icon-btn" title="返回仪表盘" aria-label="返回仪表盘">🏠</button>
  <div id="count" class="count-badge"></div>
</header>
<div id="scrim" class="scrim"></div>
<div class="layout">
  <aside id="sidebar">
    <div class="filter-chip" id="filter-chip"><span id="filter-name"></span> ✕</div>
    <div id="recent-wrap" class="recent-wrap hidden">
      <div class="recent-head">🕘 最近阅读</div>
      <div id="recent" class="recent-list"></div>
    </div>
    <div id="tree">{tree_html}</div>
    <ul class="search-results hidden" id="results"></ul>
  </aside>
  <main>
    <div class="content-wrap" id="content-wrap">
      <!-- 由 JS 注入：仪表盘视图 或 阅读器视图 -->
    </div>
  </main>
</div>
<script>
const FILES = {data_json};
const STATS = {stats_json};
{RENDERER_JS}

const $ = id => document.getElementById(id);
const wrap = $('content-wrap'), search = $('search'), tree = $('tree'),
      results = $('results'), count = $('count'),
      recentWrap = $('recent-wrap'), recentList = $('recent'),
      homeBtn = $('home-btn'),
      filterChip = $('filter-chip'), filterName = $('filter-name'),
      subCount = $('sub-count');

count.textContent = STATS.total + ' 篇';
subCount.textContent = STATS.total;

// 索引：path -> file
const byPath = {{}};
FILES.forEach(f => byPath[f.path] = f);

// 双链索引：name(小写) -> path，供 [[wiki link]] 跳转
const WIKI = {{}};
FILES.forEach(f => {{ if(!WIKI[f.name.toLowerCase()]) WIKI[f.name.toLowerCase()] = f.path; }});
function wikiLink(inner){{
  const p = String(inner).split('|');
  const target = p[0].trim();
  const alias = (p[1]||target).trim();
  const tl = target.toLowerCase();
  let path = WIKI[tl];
  if(!path){{ for(const k in WIKI){{ if(k.indexOf(tl)>=0||tl.indexOf(k)>=0){{ path=WIKI[k]; break; }} }} }}
  if(path) return '<a class="wikilink" data-target="'+path+'">'+alias+'</a>';
  return '<span class="wikilink-missing" title="未找到匹配笔记">'+alias+'</span>';
}}

// ===== 最近阅读（localStorage 记录）=====
const RECENT_KEY = 'guide-recent';
const RECENT_MAX = 8;
function getRecent(){{ try{{ return JSON.parse(localStorage.getItem(RECENT_KEY)) || []; }}catch(e){{ return []; }} }}
function pushRecent(path){{
  let list = getRecent().filter(p => p !== path);
  list.unshift(path);
  list = list.slice(0, RECENT_MAX);
  localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  renderRecent();
}}
function renderRecent(){{
  const list = getRecent().filter(p => byPath[p]);
  if(!list.length){{ recentWrap.classList.add('hidden'); return; }}
  recentWrap.classList.remove('hidden');
  recentList.innerHTML = list.map(p =>
    '<a data-path="'+p+'" title="'+p+'">'+byPath[p].name+'</a>').join('') +
    '<div class="clear" id="clear-recent">清空记录</div>';
}}
recentList.addEventListener('click', e => {{
  if(e.target.id === 'clear-recent'){{
    localStorage.removeItem(RECENT_KEY); renderRecent(); return;
  }}
  const a = e.target.closest('a[data-path]');
  if(a) openFile(a.dataset.path);
}});

// ===== 仪表盘视图 =====
let activeFilter = null;
function renderDashboard(){{
  const cats = STATS.categories.map(c => `
    <div class="cat-card${{activeFilter===c.key?' active':''}}" data-cat="${{c.key}}">
      <div class="cat-top"><span class="cat-name">${{c.name}}</span><span class="cat-count">${{c.count}}</span></div>
      <div class="cat-bar"><i style="width:${{c.pct}}%"></i></div>
    </div>`).join('');
  const rec = STATS.recent.map(r => `
    <div class="recent-item" data-path="${{r.path}}">
      <div class="ri-top"><span class="ri-name">${{r.name}}</span><span class="ri-when">${{r.when}}</span></div>
      <div class="ri-intro">${{r.intro||'(无简介)'}}</div>
      <div class="ri-path">${{r.path}}</div>
    </div>`).join('') || '<div style="color:var(--muted);padding:20px;">暂无最近更新</div>';
  wrap.innerHTML = `
    <div class="dash-hero">
      <div>
        <h2>🧵 手工文创 · 知识仪表盘</h2>
        <p>共 ${{STATS.total}} 篇笔记 · ${{STATS.categories.length}} 个分类 · 近 7 天更新 ${{STATS.weekCount}} 篇 · 点击下方卡片开始浏览</p>
      </div>
      <div class="hero-emoji">📦</div>
    </div>
    <div class="dash-section">
      <div class="section-title">📊 指标概览</div>
      <div class="stat-grid">
        <div class="stat-card"><div class="bar" style="background:var(--accent)"></div>
          <div class="ico" style="background:var(--accent-soft);color:var(--accent)">📄</div>
          <div class="num">${{STATS.total}}</div><div class="lbl">笔记总数</div></div>
        <div class="stat-card"><div class="bar" style="background:var(--c-sage)"></div>
          <div class="ico" style="background:var(--grad-sage);color:var(--c-sage)">📂</div>
          <div class="num">${{STATS.categories.length}}</div><div class="lbl">顶级分类</div></div>
        <div class="stat-card"><div class="bar" style="background:var(--c-rose)"></div>
          <div class="ico" style="background:var(--grad-rose);color:var(--c-rose)">🕘</div>
          <div class="num">${{STATS.weekCount}}</div><div class="lbl">近 7 天更新</div></div>
        <div class="stat-card"><div class="bar" style="background:var(--c-blue)"></div>
          <div class="ico" style="background:var(--grad-blue);color:var(--c-blue)">📐</div>
          <div class="num">${{STATS.planCount}}</div><div class="lbl">方案库条目</div></div>
      </div>
    </div>
    <div class="dash-section">
      <div class="section-title">🗂 分类概览 · 点击筛选目录</div>
      <div class="cat-grid">${{cats}}</div>
    </div>
    <div class="dash-section">
      <div class="section-title">🆕 最近更新</div>
      <div class="recent-grid">${{rec}}</div>
    </div>`;
  wrap.querySelectorAll('.cat-card').forEach(card => {{
    card.addEventListener('click', () => toggleFilter(card.dataset.cat));
  }});
  wrap.querySelectorAll('.recent-item').forEach(it => {{
    it.addEventListener('click', () => openFile(it.dataset.path));
  }});
}}

// ===== 分类筛选（侧栏）=====
function toggleFilter(cat){{
  activeFilter = (activeFilter === cat) ? null : cat;
  applyFilter();
  if(activeFilter) renderDashboard();  // 刷新高亮
}}
function applyFilter(){{
  if(!activeFilter){{
    filterChip.classList.remove('show');
    document.querySelectorAll('aside details.dir, aside a.file').forEach(el => el.classList.remove('hidden'));
    return;
  }}
  const name = STATS.categories.find(c => c.key===activeFilter)?.name || activeFilter;
  filterName.textContent = name;
  filterChip.classList.add('show');
  // 隐藏不在该分类下的文件
  document.querySelectorAll('aside a.file').forEach(a => {{
    a.classList.toggle('hidden', !a.dataset.path.startsWith(activeFilter + '/'));
  }});
  // 隐藏没有可见文件的 details
  document.querySelectorAll('aside details.dir').forEach(d => {{
    const hasVisible = d.querySelector('a.file:not(.hidden)');
    d.classList.toggle('hidden', !hasVisible);
  }});
}}
filterChip.addEventListener('click', () => {{ activeFilter=null; applyFilter(); renderDashboard(); }});

// ===== 阅读器 =====
let current = null;
function openFile(path){{
  const f = byPath[path];
  if(!f) return;
  current = path;
  pushRecent(path);
  document.querySelectorAll('a.file').forEach(a =>
    a.classList.toggle('active', a.dataset.path === path));
  const html = '<a class="back-link" id="back">← 返回仪表盘</a>' +
    '<div class="breadcrumb">📂 ' + path + '</div>' +
    '<div class="reader">' + renderMarkdown(f.content) + '</div>';
  wrap.innerHTML = html;
  $('back').addEventListener('click', goHome);
  buildToc();
  document.querySelector('main').scrollTo({{top:0}});
  if(location.hash !== '#' + path) history.replaceState(null,'','#'+path);
}}

// 长文目录（TOC）：抽取 h2/h3 生成可点击大纲
function buildToc(){{
  const reader = wrap.querySelector('.reader');
  if(!reader) return;
  const heads = reader.querySelectorAll('h2,h3');
  if(heads.length < 3) return;
  let html=''; let n=0;
  heads.forEach(h => {{
    const id='toc-h'+(++n); h.id=id;
    const cls = h.tagName==='H3' ? 'toc-link toc-sub' : 'toc-link';
    html += '<a class="'+cls+'" data-id="'+id+'">'+h.textContent+'</a>';
  }});
  const box = document.createElement('div');
  box.className='toc';
  box.innerHTML='<div class="toc-title">📑 本页目录</div><div class="toc-body">'+html+'</div>';
  reader.insertBefore(box, reader.firstChild);
}}
// TOC 点击：平滑滚动定位
wrap.addEventListener('click', e => {{
  const lk = e.target.closest('a.toc-link');
  if(!lk) return;
  e.preventDefault();
  const el = document.getElementById(lk.dataset.id);
  if(!el) return;
  const main = document.querySelector('main');
  const top = el.getBoundingClientRect().top + main.scrollTop - 76;
  main.scrollTo({{top, behavior:'smooth'}});
}});
function goHome(){{
  current = null;
  document.querySelectorAll('a.file').forEach(a => a.classList.remove('active'));
  if(location.hash) history.replaceState(null,'','#');
  renderDashboard();
  document.querySelector('main').scrollTo({{top:0}});
}}
homeBtn.addEventListener('click', goHome);

// 绑定文件点击 / 双链点击
document.addEventListener('click', e => {{
  const a = e.target.closest('a.file');
  if(a){{ e.preventDefault(); openFile(a.dataset.path); return; }}
  const wl = e.target.closest('a.wikilink');
  if(wl){{ e.preventDefault(); openFile(wl.dataset.target); }}
}});

// 搜索
function hl(text, q){{
  if(!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if(i<0) return text;
  return text.slice(0,i) + '<mark>' + text.slice(i,i+q.length) + '</mark>' + text.slice(i+q.length);
}}
function runSearch(q){{
  q = q.trim();
  if(!q){{
    tree.classList.remove('hidden'); results.classList.add('hidden'); results.innerHTML='';
    applyFilter();
    renderRecent();
    count.textContent = STATS.total + ' 篇'; return;
  }}
  recentWrap.classList.add('hidden');
  tree.classList.add('hidden'); results.classList.remove('hidden');
  filterChip.classList.remove('show');
  const ql = q.toLowerCase();
  const matched = [];
  for(const f of FILES){{
    const byName = f.name.toLowerCase().includes(ql) || f.path.toLowerCase().includes(ql);
    const pi = f.plain.toLowerCase().indexOf(ql);
    if(byName || pi >= 0){{
      let snippet = '';
      if(pi >= 0){{
        const start = Math.max(0, pi-30);
        snippet = (start>0?'…':'') + f.plain.slice(start, pi+q.length+60) + '…';
      }}
      matched.push({{f, snippet}});
    }}
  }}
  count.textContent = '找到 ' + matched.length + ' 篇';
  results.innerHTML = matched.map(m => {{
    const snip = m.snippet ? '<div class="snippet">' + hl(m.snippet, q) + '</div>' : '';
    return '<li data-path="'+m.f.path+'">' +
      '<div class="path">' + m.f.path + '</div>' +
      '<div class="name">' + hl(m.f.name, q) + '</div>' +
      snip + '</li>';
  }}).join('') || '<li style="color:var(--muted);text-align:center;padding:40px;">未找到匹配内容</li>';
}}
search.addEventListener('input', e => runSearch(e.target.value));
results.addEventListener('click', e => {{
  const li = e.target.closest('li[data-path]');
  if(li){{ openFile(li.dataset.path); search.value=''; runSearch(''); }}
}});

// 快捷键：/ 聚焦搜索，Esc 清空
document.addEventListener('keydown', e => {{
  if(e.key==='/' && document.activeElement !== search){{ e.preventDefault(); search.focus(); }}
  if(e.key==='Escape'){{
    if(search.value){{ search.value=''; runSearch(''); search.blur(); }}
    else if(current){{ goHome(); }}
  }}
}});

// 启动
renderRecent();
const initHash = decodeURIComponent(location.hash.slice(1));
if(initHash && byPath[initHash]) openFile(initHash);
else renderDashboard();
</script>
</body>
</html>"""
    return html


def main():
    items = collect_md()
    stats = build_stats(items)
    tree = build_tree(items)
    tree_html = render_tree(tree)
    html = build_html(items, tree_html, stats)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ 已生成仪表盘: {OUTPUT}")
    print(f"  收录 {stats['total']} 篇笔记 · {len(stats['categories'])} 个分类 · 近 7 天更新 {stats['weekCount']} 篇")
    print(f"  约 {len(html)//1024} KB")


if __name__ == "__main__":
    main()
