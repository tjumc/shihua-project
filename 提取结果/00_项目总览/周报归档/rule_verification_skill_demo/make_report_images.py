from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT.parent
FONT_REG = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(size, bold=False):
    path = FONT_BOLD if bold and FONT_BOLD.exists() else FONT_REG
    return ImageFont.truetype(str(path), size)


def text_size(draw, text, fnt):
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw, text, fnt, max_width):
    lines = []
    for part in text.split("\n"):
        current = ""
        for ch in part:
            candidate = current + ch
            if text_size(draw, candidate, fnt)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def draw_centered(draw, box, text, fnt, fill="#1f2937", line_gap=8):
    x1, y1, x2, y2 = box
    lines = wrap_text(draw, text, fnt, x2 - x1 - 36)
    heights = [text_size(draw, line, fnt)[1] for line in lines]
    total_h = sum(heights) + line_gap * (len(lines) - 1)
    y = y1 + (y2 - y1 - total_h) / 2
    for line, h in zip(lines, heights):
        w, _ = text_size(draw, line, fnt)
        draw.text((x1 + (x2 - x1 - w) / 2, y), line, font=fnt, fill=fill)
        y += h + line_gap


def round_box(draw, box, fill, outline, width=3, radius=22):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw, start, end, color="#64748b", width=5):
    draw.line([start, end], fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 >= x1 else -1
        pts = [(x2, y2), (x2 - 16 * direction, y2 - 10), (x2 - 16 * direction, y2 + 10)]
    else:
        direction = 1 if y2 >= y1 else -1
        pts = [(x2, y2), (x2 - 10, y2 - 16 * direction), (x2 + 10, y2 - 16 * direction)]
    draw.polygon(pts, fill=color)


def save(img, name):
    path = OUT_DIR / name
    img.save(path)
    print(path)


def draw_demo_flow():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), "#f8fafc")
    draw = ImageDraw.Draw(img)
    title_f = font(44, True)
    sub_f = font(24)
    box_title_f = font(28, True)
    box_f = font(24)
    small_f = font(20)

    draw.text((80, 46), "规则核验 Skill Demo 流程", font=title_f, fill="#0f172a")
    draw.text((80, 106), "展示范围：已提取规则表 -> 核验数据集 -> 自动核验判定", font=sub_f, fill="#475569")

    layers = [
        ("输入层", "#dbeafe", "#2563eb"),
        ("Skill 自动处理", "#dcfce7", "#16a34a"),
        ("盲审回填层", "#ffedd5", "#f97316"),
        ("合并与判定层", "#ede9fe", "#7c3aed"),
        ("输出层", "#e2e8f0", "#475569"),
    ]
    y_positions = [190, 360, 535, 710, 885]
    for (label, fill, outline), y in zip(layers, y_positions):
        draw.rounded_rectangle((70, y, 270, y + 110), radius=18, fill=fill, outline=outline, width=3)
        draw_centered(draw, (70, y, 270, y + 110), label, box_title_f, fill="#0f172a")

    boxes = {
        "input": (360, 185, 710, 305, "已有规则汇总表\n规则编号 / 规则内容 / 来源文件 / 页码", "#eff6ff", "#2563eb"),
        "mask": (360, 355, 710, 475, "生成 mask1 / mask2\n参数类字段 + 语义类字段", "#f0fdf4", "#16a34a"),
        "blind": (820, 355, 1180, 475, "导出双智能体盲审输入\n不暴露规则内容/原文/JSON", "#f0fdf4", "#16a34a"),
        "a1": (360, 530, 710, 650, "Agent 1\n回填 mask1：数值 / 单位 / 阈值", "#fff7ed", "#f97316"),
        "a2": (820, 530, 1180, 650, "Agent 2\n回填 mask2：动作 / 对象 / 条件", "#fff7ed", "#f97316"),
        "merge": (360, 705, 710, 825, "合并回填结果\n生成 filled 表", "#f5f3ff", "#7c3aed"),
        "judge": (820, 705, 1180, 825, "自动判定\n人工核验mask1/2 + 人工核对", "#f5f3ff", "#7c3aed"),
        "verified": (360, 880, 710, 1000, "最终核验表\nrule_content_verified.xlsx", "#f1f5f9", "#475569"),
        "report": (820, 880, 1180, 1000, "核验报告\nverification_report.md", "#f1f5f9", "#475569"),
    }
    for key, (x1, y1, x2, y2, txt, fill, outline) in boxes.items():
        round_box(draw, (x1, y1, x2, y2), fill, outline)
        draw_centered(draw, (x1, y1, x2, y2), txt, box_f)

    arrow(draw, (535, 305), (535, 355))
    arrow(draw, (710, 415), (820, 415))
    arrow(draw, (535, 475), (535, 530))
    arrow(draw, (1000, 475), (1000, 530))
    arrow(draw, (535, 650), (535, 705))
    arrow(draw, (1000, 650), (1000, 705))
    arrow(draw, (710, 765), (820, 765))
    arrow(draw, (535, 825), (535, 880))
    arrow(draw, (1000, 825), (1000, 880))

    # Evidence panel.
    panel = (1290, 185, 1810, 1000)
    draw.rounded_rectangle(panel, radius=28, fill="#ffffff", outline="#cbd5e1", width=3)
    draw.text((1330, 230), "Demo 验证结果", font=font(34, True), fill="#0f172a")
    result_items = [
        ("样例规则", "3 条", "#2563eb"),
        ("无需人工核对", "2 条", "#16a34a"),
        ("需要人工核对", "1 条", "#dc2626"),
    ]
    y = 310
    for label, value, color in result_items:
        draw.rounded_rectangle((1330, y, 1770, y + 90), radius=18, fill="#f8fafc", outline="#e2e8f0", width=2)
        draw.text((1360, y + 24), label, font=font(25, True), fill="#334155")
        draw.text((1655, y + 20), value, font=font(30, True), fill=color, anchor="la")
        y += 120
    draw.text((1330, 690), "边界说明", font=font(28, True), fill="#0f172a")
    notes = [
        "当前展示：规则核验模块闭环",
        "输入是已提取规则表",
        "不包含原始文件自动抽取",
        "不包含自动回源填空",
    ]
    y = 745
    for note in notes:
        draw.text((1350, y), "• " + note, font=small_f, fill="#475569")
        y += 44

    save(img, "rule_verification_demo_flow.png")


def draw_roadmap():
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), "#f8fafc")
    draw = ImageDraw.Draw(img)
    draw.text((80, 50), "当前能力与后续阶段规划", font=font(44, True), fill="#0f172a")
    draw.text((80, 110), "从规则核验模块扩展到“抽取-更新-核验”数据集构建闭环", font=font(24), fill="#475569")

    current = (90, 205, 620, 870)
    draw.rounded_rectangle(current, radius=28, fill="#ffffff", outline="#2563eb", width=4)
    draw.text((130, 250), "本周已完成", font=font(34, True), fill="#1d4ed8")
    done_items = [
        "规则核验 skill 初版",
        "mask1 / mask2 字段设计",
        "双智能体盲审输入",
        "回填合并与自动判定",
        "可展示 demo 与核验报告",
    ]
    y = 330
    for item in done_items:
        draw.text((145, y), "• " + item, font=font(24), fill="#1e293b")
        y += 70
    draw.rounded_rectangle((140, 720, 570, 805), radius=18, fill="#dbeafe", outline="#93c5fd", width=2)
    draw_centered(draw, (140, 720, 570, 805), "当前边界：已有规则表 -> 核验结果", font(24, True), fill="#1e3a8a")

    stages = [
        ("阶段一", "新数据文件接入", "文件清单 / 哈希 / 更新时间\n识别新增与修改文件", "#dbeafe", "#2563eb"),
        ("阶段二", "已提取规则更新与替换", "新增 / 修改 / 重复 / 冲突\n形成规则变更记录", "#dcfce7", "#16a34a"),
        ("阶段三", "通用规则融合", "完整性 / 来源追溯 / 单位一致\nJSON 合法性等通用规则", "#ffedd5", "#f97316"),
        ("阶段四", "抽取-更新-核验闭环", "串联提取 skill 与核验 skill\n形成完整数据集构建流程", "#ede9fe", "#7c3aed"),
    ]
    x0 = 720
    y0 = 220
    w = 510
    h = 150
    gap = 55
    for i, (stage, title, desc, fill, outline) in enumerate(stages):
        y = y0 + i * (h + gap)
        draw.rounded_rectangle((x0, y, x0 + w, y + h), radius=24, fill=fill, outline=outline, width=4)
        draw.text((x0 + 32, y + 24), stage, font=font(24, True), fill=outline)
        draw.text((x0 + 135, y + 22), title, font=font(28, True), fill="#0f172a")
        draw_centered(draw, (x0 + 30, y + 68, x0 + w - 30, y + h - 18), desc, font(22), fill="#334155")
        if i < len(stages) - 1:
            arrow(draw, (x0 + w / 2, y + h), (x0 + w / 2, y + h + gap - 8), color="#94a3b8", width=5)

    # Next-week emphasis.
    panel = (1320, 220, 1815, 595)
    draw.rounded_rectangle(panel, radius=28, fill="#ffffff", outline="#cbd5e1", width=3)
    draw.text((1360, 265), "下周优先尝试", font=font(32, True), fill="#0f172a")
    draw.rounded_rectangle((1360, 330, 1775, 410), radius=18, fill="#dbeafe", outline="#2563eb", width=3)
    draw_centered(draw, (1360, 330, 1775, 410), "阶段一：新数据文件接入", font(26, True), fill="#1e3a8a")
    for j, item in enumerate(["source_manifest 样例", "新增/修改文件识别", "接入抽取流程方案"]):
        draw.text((1370, 455 + 45 * j), "• " + item, font=font(22), fill="#475569")

    panel2 = (1320, 650, 1815, 870)
    draw.rounded_rectangle(panel2, radius=28, fill="#fff7ed", outline="#fb923c", width=3)
    draw.text((1360, 695), "最终目标", font=font(32, True), fill="#9a3412")
    draw_centered(draw, (1360, 755, 1775, 830), "新数据接入 -> 增量抽取 -> 更新替换 -> 通用规则融合 -> 自动核验", font(22), fill="#7c2d12")

    save(img, "rule_pipeline_roadmap.png")


if __name__ == "__main__":
    draw_demo_flow()
    draw_roadmap()
