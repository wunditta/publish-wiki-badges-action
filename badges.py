#!/usr/bin/env python3
"""Expand the badge shorthands of wiki pages into inline SVG badges (see README.md).

Usage: python3 badges.py <wiki folder> [<badges.json>]   (default config: badges.json next to this file)
The pages are changed in place; the SVG files go to <wiki folder>/<global.dir>/.

badges.json (keys starting with "//" are comments, "" means "inherit", trailing commas are tolerated):
  global            settings that act between badges or on the page: dir, align, baseline, height, codeHeight, font,
                    fontSize, radius, padding, altGap, tableMinWidth, only_named_badges, strict_name_check
  defaults          settings every badge inherits: textColor, color, scale, shift, codeShift, badgesInCodeSpans, icon{...}
  type_specs        badge types: "default" ([name] tokens), "file" (page links [**name**](name.md)) and any others;
                    each may override the defaults; a badge belongs to the first type that lists its name
  colors_per_badge  {type: {name: color}} - the background colour per badge name
"""
import json, re, sys, pathlib, hashlib

CHARWIDTH = 0.62      # fallback glyph width (multiple of the font size) for characters not in VERDANA
TEXTMARGIN = 0.08     # safety margin on the measured text width (room for fallback fonts)

# Verdana advance widths in 1/2048 em; the text is centred, so a small error only moves the padding
VERDANA = {}
for chars, w in [("a", 1228), ("b", 1259), ("c", 1061), ("d", 1259), ("e", 1200), ("f", 702), ("g", 1259), ("h", 1265), ("i", 554), ("j", 666),
                 ("k", 1159), ("l", 554), ("m", 1960), ("n", 1265), ("o", 1227), ("p", 1259), ("q", 1259), ("r", 865), ("s", 1046), ("t", 772),
                 ("u", 1265), ("v", 1172), ("w", 1660), ("x", 1172), ("y", 1172), ("z", 1046),
                 ("A", 1395), ("B", 1413), ("C", 1430), ("D", 1593), ("E", 1294), ("F", 1178), ("G", 1588), ("H", 1540), ("I", 865), ("J", 937),
                 ("K", 1435), ("L", 1165), ("M", 1727), ("N", 1546), ("O", 1612), ("P", 1235), ("Q", 1612), ("R", 1424), ("S", 1400), ("T", 1262),
                 ("U", 1499), ("V", 1395), ("W", 2033), ("X", 1395), ("Y", 1262), ("Z", 1395),
                 ("äàáâãå", 1228), ("ëèéê", 1200), ("ïìíî", 554), ("öòóôõø", 1227), ("üùúû", 1265), ("ÄÀÁÂÃÅ", 1395), ("ËÈÉÊ", 1294),
                 ("ÖÒÓÔÕØ", 1612), ("ÜÙÚÛ", 1499), ("ß", 1259), ("ç", 1061), ("Ç", 1430), ("ñ", 1265), ("Ñ", 1546),
                 ("0123456789", 1303), ("{}", 1303), ("/", 933), ("-", 933), ("_", 1303), (".", 745), (" ", 720), ("[]", 933), ("()", 850),
                 (",", 745), (":", 822), (";", 822), ("!", 822), ("?", 1104), ("+", 1676), ("=", 1676), ("<>", 1676), ("*", 1446), ("#", 1676),
                 ("&", 1489), ("@", 2048), ("%", 2173), ("'", 459), ('"', 931), ("|", 1352), ("~", 1676), ("^", 1676), ("$", 1303)]:
    for ch in chars:
        VERDANA[ch] = w / 2048

# ---------------------------------------------------------------- configuration

def load_config(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r",(\s*[}\]])", r"\1", text)          # trailing commas
    cfg = json.loads(text)

    def clean(v):                                       # drop "//" keys at every level
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items() if not k.startswith("//")}
        return v
    return clean(cfg)

def merged(*layers):
    """later layers override earlier ones; "" and missing keys inherit; nested dicts merge"""
    out = {}
    for layer in layers:
        for k, v in (layer or {}).items():
            if isinstance(v, dict):
                out[k] = merged(out.get(k, {}), v)
            elif v != "" and v is not None:
                out[k] = v
    return out

class Config:
    def __init__(self, path):
        cfg = load_config(path)
        self.dir = path.parent
        g = cfg.get("global", {})
        self.badgedir = g.get("dir", "badges")
        self.align = g.get("align", "absmiddle")
        self.baseline = float(g.get("baseline", 0.37))
        self.height = float(g.get("height", 16))
        self.codeheight = float(g.get("codeHeight", self.height))
        self.font = g.get("font", "Verdana, DejaVu Sans, sans-serif")
        self.fontsize = float(g.get("fontSize", 0.8))
        self.radius = float(g.get("radius", 0.25))
        self.padding = float(g.get("padding", 0.16))
        self.altgap = g.get("altGap", "&thinsp;")
        # inside code spans a gap that is only white space is dropped (monospace renders a thin space as a full space)
        self.altgapcode = "" if re.fullmatch(r"(\s|&(thinsp|nbsp|ensp|emsp|hairsp|#x?[0-9a-fA-F]+);)*", self.altgap) else self.altgap
        self.strict = bool(g.get("strict_name_check", False))
        self.tablemin = bool(g.get("tableMinWidth", True))
        self.onlynamed = bool(g.get("only_named_badges", True))
        defaults = merged({"textColor": "#000000", "color": "#888888", "scale": 1, "shift": 0, "badgesInCodeSpans": True,
                           "icon": {"name": "", "rotate": 0, "height": 0.84, "padding": 0.2, "gap": 0.12, "color": ""}},
                          cfg.get("defaults", {}))
        specs = cfg.get("type_specs", {})
        self.types = {}                                  # type -> effective settings
        for t in list(specs) + [t for t in ("default", "file") if t not in specs]:
            s = merged(defaults, specs.get(t, {}))
            if "codeShift" not in s:
                s["codeShift"] = s["shift"]
            self.types[t] = s
        self.colors = cfg.get("colors_per_badge", {})    # type -> {name: color}
        self.name_type = {}                              # badge name -> type (first type that lists it; file excluded)
        for t in self.types:
            if t == "file":
                continue
            for name in self.colors.get(t, {}):
                self.name_type.setdefault(name, t)
        self.icons = {}                                  # icon file name -> (viewBox w, viewBox h, inner svg)

    def type_of(self, name):
        t = self.name_type.get(name)
        if t is None and not self.onlynamed:
            t = "default"
        return t

    def color_of(self, t, name):
        return self.colors.get(t, {}).get(name) or self.types[t]["color"]

    def icon(self, filename):
        """(viewBox width, viewBox height, inner markup) of an SVG file next to badges.json; None if no file"""
        if not filename:
            return None
        if filename not in self.icons:
            p = self.dir / filename
            if not p.is_file():
                sys.exit("Badges: icon file not found: %s" % p)
            svg = p.read_text(encoding="utf-8")
            m = re.search(r"<svg\b[^>]*>", svg, re.S)
            vb = re.search(r'viewBox="([^"]+)"', m.group(0)) if m else None
            if not m or not vb:
                sys.exit("Badges: icon %s needs an <svg> root with a viewBox" % p)
            x, y, w, h = (float(v) for v in vb.group(1).replace(",", " ").split())
            inner = svg[m.end():svg.rfind("</svg>")]
            self.icons[filename] = (x, y, w, h, inner)
        return self.icons[filename]

CFG = None            # the Config
WIKI = None           # the wiki folder
WRITTEN = {}          # badge key -> file name
LASTWIDTH = {}        # file name -> width in px (for tableMinWidth)

# ---------------------------------------------------------------- SVG

def text_width(text, fs):
    return sum(VERDANA.get(ch, CHARWIDTH) for ch in text) * fs * (1 + TEXTMARGIN)

def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def icon_svg(spec, x0, H, textcolor):
    """the icon at x0 (left edge), vertically centred in a badge of height H; returns (markup, width)"""
    ic = CFG.icon(spec.get("name"))
    if ic is None:
        return "", 0.0
    vx, vy, vw, vh, inner = ic
    rot = float(spec.get("rotate", 0)) % 360
    pw, ph = (vh, vw) if rot % 180 == 90 else (vw, vh)       # box after rotation
    ih = H * float(spec.get("height", 0.84))
    sc = ih / ph
    iw = pw * sc
    y0 = (H - ih) / 2
    w0, h0 = vw * sc, vh * sc                                # size before rotation
    cx, cy = x0 + iw / 2, y0 + ih / 2                        # centre of the box
    color = spec.get("color") or textcolor
    markup = (f'<g fill="{color}" color="{color}" transform="rotate({rot:g},{cx:.2f},{cy:.2f})">'
              f'<svg x="{cx - w0/2:.2f}" y="{cy - h0/2:.2f}" width="{w0:.2f}" height="{h0:.2f}" viewBox="{vx:g} {vy:g} {vw:g} {vh:g}" '
              f'preserveAspectRatio="xMidYMid meet">{inner}</svg></g>')
    return markup, iw

def lookup_name(t, text):
    """the name whose colour the badge takes: the text itself (file type, strict mode), else the last name in it"""
    if t == "file" or CFG.strict:
        return text
    names = re.findall(NAME, text)
    return names[-1] if names else text

def badge_file(t, text, incode):
    """write (once) the SVG of a badge of type t and return its URL for <img src>"""
    s = CFG.types[t]
    fill = CFG.color_of(t, lookup_name(t, text))
    H = round((CFG.codeheight if incode else CFG.height) * float(s["scale"]), 1)
    S = float(s["codeShift"] if incode else s["shift"])
    key = (t, text, fill, H, S)
    if key not in WRITTEN:
        fs = H * CFG.fontsize
        tw = round(text_width(text, fs), 1)
        pad = H * CFG.padding
        icon, iw = icon_svg(s["icon"], H * float(s["icon"].get("padding", 0.2)), H, s["textColor"])
        left = (H * float(s["icon"].get("padding", 0.2)) + iw + H * float(s["icon"].get("gap", 0.12))) if icon else pad
        w = round(left + tw + pad, 1)
        r = round(H * CFG.radius, 1)
        band = round(abs(S) * H, 1)                          # transparent space above (shift<0) or below (shift>0)
        top = band if S < 0 else 0
        total = round(H + band, 1)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{total}" viewBox="0 0 {w} {total}" role="img" aria-label="{html_escape(text)}">'
               f'<g transform="translate(0,{top})"><rect width="{w}" height="{H}" rx="{r}" fill="{fill}"/>{icon}'
               f'<text x="{left + tw/2:.1f}" y="{H/2 + fs*CFG.baseline:.1f}" text-anchor="middle" '
               f'font-family="{CFG.font}" font-size="{fs:.1f}" fill="{s["textColor"]}">{html_escape(text)}</text></g></svg>')
        slug = re.sub(r"[^A-Za-z0-9]+", "-", text.replace("{}", "-tab")).strip("-") or "badge"
        if re.search(r"[^A-Za-z0-9{}/_.-]", text):
            slug += "-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:4]      # decoration: keep different texts apart
        name = f"{t}-{slug}-{fill.lstrip('#')}-{H:g}" + (f"-s{S:g}".replace(".", "_") if S else "") + ".svg"
        (WIKI / CFG.badgedir).mkdir(parents=True, exist_ok=True)
        (WIKI / CFG.badgedir / name).write_text(svg, encoding="utf-8")
        WRITTEN[key] = name
        LASTWIDTH[name] = w
    return WRITTEN[key], H, S

def img(t, text, incode=False):
    name, H, S = badge_file(t, text, incode)
    total = round(H * (1 + abs(S)))
    return f'<img alt="{html_escape(text)}" src="{CFG.badgedir}/{name}" height="{total}" align="{CFG.align}">'

# ---------------------------------------------------------------- tokens

NAME = r"[A-Za-z0-9_.-]+"
TOKEN = re.compile(r"\[([^\[\]\s][^\[\]]*)\](?![(\[])")          # anything in brackets that is not a link or a footnote
DECOR = re.compile(r"^(%s)" % NAME)
GROUP = re.compile(r"^\(([^()]+)\)(.*)$")
FILE_LINK = re.compile(r"\[([*_`]*)([A-Za-z0-9_-]+)\1\]\((?:\./)?([A-Za-z0-9_-]+)(?:\.md)?\)")

def name_in(part):
    """lenient mode: (name, text) of one alternative - the name is the first run of name characters, the rest is decoration
    kept in the badge text; None if there is no name"""
    m = re.search(NAME, part)
    if not m:
        return None
    return m.group(0), part

def split_token(inner):
    """the badges of one token as [(type, text), ...]; None if any name is unknown.
    strict: the whole content is the name. lenient: [a/b{}] one badge per alternative, [(a/b){}] one badge
    for the group (coloured like its last name), decoration characters kept in the text."""
    if CFG.strict:
        t = CFG.type_of(inner)
        return None if t is None else [(t, inner)]
    g = GROUP.match(inner)
    if g:
        names = [name_in(p) for p in g.group(1).split("/")]
        if any(n is None for n in names):
            return None
        types = [CFG.type_of(n[0]) for n in names]
        if any(t is None for t in types):
            return None
        return [(types[-1], g.group(1) + g.group(2))]
    out = []
    for part in inner.split("/"):
        n = name_in(part)
        if n is None:
            return None
        t = CFG.type_of(n[0])
        if t is None:
            return None
        out.append((t, part))
    return out

def token_html(inner, incode):
    parts = split_token(inner)
    if parts is None:
        return None
    if incode and not all(CFG.types[t]["badgesInCodeSpans"] for t, _ in parts):
        return None
    gap = CFG.altgapcode if incode else CFG.altgap
    return gap.join(img(t, text, incode) for t, text in parts)

def convert_code_span(span):
    inner = span[1:-1]
    if not TOKEN.search(inner):
        return span
    pieces, pos, found = [], 0, False
    for m in TOKEN.finditer(inner):
        html = token_html(m.group(1), True)
        if html is None:
            continue
        found = True
        pieces.append(html_escape(inner[pos:m.start()]))
        pieces.append(html)
        pos = m.end()
    if not found:
        return span
    pieces.append(html_escape(inner[pos:]))
    return "<code>" + "".join(pieces) + "</code>"

def convert_text(text):
    def tok(m):
        html = token_html(m.group(1), False)
        return html if html is not None else m.group(0)
    return TOKEN.sub(tok, text)

def convert_file_links(line, pages):
    """[name](name.md), [**name**](name.md), [`name`](name.md) -> badge linking to the page, when the page exists and the label is
    the page name; matched on the whole line (the label may hold a code span)"""
    def link(m):
        label, target = m.group(2), m.group(3)
        if target in pages and label.lower() == target.lower():
            return f'<a href="./{target}">{img("file", target)}</a>'
        return m.group(0)
    return FILE_LINK.sub(link, line)

# ---------------------------------------------------------------- tables

CELL_IMG = re.compile(r'<img alt="[^"]*" src="[^"]*/([^"/]+\.svg)"[^>]*>')

def badge_only_width(cell):
    inner = cell.strip()
    if not inner:
        return 0
    rest = re.sub(r"</?a[^>]*>|&thinsp;", "", CELL_IMG.sub("", inner)).strip()
    if rest:
        return 0
    return sum(LASTWIDTH.get(m.group(1), 0) for m in CELL_IMG.finditer(inner))

def pad_table(lines):
    """a column of badge-only cells gets its header widened with &nbsp; on both sides up to the widest badge,
    so the column cannot shrink the images; the rows stay untouched and the header text stays centred"""
    if len(lines) < 3:
        return lines
    rows = [l.split("|") for l in lines]
    head = rows[0]
    for i in range(len(head)):
        text = head[i].strip()
        if not text:
            continue
        widest = max((badge_only_width(r[i]) for r in rows[2:] if i < len(r)), default=0)
        have = text_width(re.sub(r"[*_`]", "", text), 16)
        if widest <= have:
            continue
        n = int((widest - have) / (16 * 0.28)) + 2
        half = "&nbsp;" * ((n + 1) // 2)
        head[i] = " " + half + text + half + " "
    lines[0] = "|".join(head)
    return lines

# ---------------------------------------------------------------- files

def convert_file(path, pages):
    src = path.read_text(encoding="utf-8")
    out, fence = [], False
    for line in src.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        if fence:
            out.append(line)
            continue
        line = convert_file_links(line, pages)
        parts = re.split(r"(`[^`\n]*`)", line)           # code spans
        for i in range(0, len(parts), 2):
            parts[i] = convert_text(parts[i])
        for i in range(1, len(parts), 2):
            parts[i] = convert_code_span(parts[i])
        out.append("".join(parts))
    if CFG.tablemin:
        i = 0
        while i < len(out):
            if out[i].lstrip().startswith("|"):
                j = i
                while j < len(out) and out[j].lstrip().startswith("|"):
                    j += 1
                out[i:j] = pad_table(out[i:j])
                i = j
            else:
                i += 1
    new = "\n".join(out)
    if new != src:
        path.write_text(new, encoding="utf-8")
        print(f"Badges: converted {path.name}")

def main():
    global CFG, WIKI
    here = pathlib.Path(__file__).resolve().parent
    WIKI = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "wiki")
    CFG = Config(pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else here / "badges.json")
    pages = {p.stem for p in WIKI.glob("*.md")}
    for p in sorted(WIKI.glob("*.md")):
        convert_file(p, pages)

if __name__ == "__main__":
    main()
