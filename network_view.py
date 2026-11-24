"""A responsive transmission-network diagram for the desktop analyzer."""
import math
import tkinter as tk
from collections import defaultdict
from tkinter import font as tkfont


PAPER = "#f8faf8"
TEAL = "#007d71"
RED = "#ba4538"
INK = "#173b3b"
MUTED = "#647875"


class NetworkView(tk.Canvas):
    """Render the input topology and, when available, the solved line flows."""

    def __init__(self, parent, **kwargs):
        options = dict(background=PAPER, highlightthickness=0, borderwidth=0, width=320, height=220)
        options.update(kwargs)
        super().__init__(parent, **options)
        self.buses, self.lines = {}, {}
        self.reference = self.outage = self.result = None
        self.hints = {}
        self.label_font = tkfont.Font(self, family="Segoe UI", size=9, weight="bold")
        self.node_font = tkfont.Font(self, family="Segoe UI", size=10, weight="bold")
        self.small_font = tkfont.Font(self, family="Segoe UI", size=8)
        self.bind("<Configure>", self._draw)
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda _: self.delete("hint"))

    def show(self, buses, lines, reference, result=None, outage=None):
        self.buses, self.lines = buses, lines
        self.reference, self.result, self.outage = reference, result, outage
        self._draw()

    def _positions(self, width, height):
        ids = list(self.buses)
        # Start the ring at the reference bus and retain input order around it.
        if self.reference in ids:
            offset = ids.index(self.reference)
            ids = ids[offset:] + ids[:offset]
        unit = [(math.sin(i * math.tau / len(ids)), -math.cos(i * math.tau / len(ids)))
                for i in range(len(ids))]
        xs, ys = zip(*unit)
        margin_x = max(min(55, max(26, width * .12)), (width - height * 3.25) / 2)
        margin_top = 43
        margin_bottom = min(38, max(25, height * .14))
        return {bus: (margin_x + (x - min(xs)) / max(1, max(xs) - min(xs)) * (width - 2 * margin_x),
                      margin_top + (y - min(ys)) / max(1, max(ys) - min(ys)) * (height - margin_top - margin_bottom))
                for bus, (x, y) in zip(ids, unit)}

    def _fit(self, text, width, font):
        if font.measure(text) <= width:
            return text
        visible = ""
        for letter in text:
            if font.measure(visible + letter + "…") > width:
                break
            visible += letter
        return visible + "…"

    def _draw(self, _event=None):
        self.delete("all")
        self.hints.clear()
        width, height = self.winfo_width(), self.winfo_height()
        if min(width, height) < 40:
            return
        for x in range(12, width, 24):
            for y in range(12, height, 24):
                self.create_line(x, y, x + 1, y, fill="#d4dfda", width=1)
        if not self.buses:
            self.create_text(width / 2, height / 2, text="No grid loaded", fill=MUTED, font=self.small_font)
            return

        positions = self._positions(width, height)
        node_radius = 16 if len(positions) < 8 else 14
        occupied = [(x - node_radius - 3, y - node_radius - 3, x + node_radius + 3, y + node_radius + 3)
                    for x, y in positions.values()]
        ref_x, ref_y = positions.get(self.reference, (0, 0))
        occupied.append((ref_x - 33, ref_y - node_radius - 18, ref_x + 33, ref_y - node_radius))

        flows = {r["line"]: r for r in self.result["flows"]} if self.result else {}
        groups = defaultdict(list)
        for line, (start, end, _reactance, _limit) in self.lines.items():
            groups[tuple(sorted((start, end)))].append(line)

        labels = []
        for i, (line, (start, end, _reactance, limit)) in enumerate(self.lines.items()):
            tag = f"edge_{i}"
            row = flows.get(line)
            open_line = line == self.outage or (row and row["state"] == "OUT")
            overloaded = row and row["state"] == "OVERLOAD"
            color = "#87948f" if open_line else RED if overloaded else TEAL if row else "#678a84"
            start_xy, end_xy = positions[start], positions[end]
            pair = tuple(sorted((start, end)))
            group = groups[pair]
            lane = group.index(line) - (len(group) - 1) / 2
            bend = lane * min(32, 110 / len(group)) * (1 if start == pair[0] else -1)
            x0, y0 = start_xy
            x1, y1 = end_xy
            dx, dy = x1 - x0, y1 - y0
            length = max(1, math.hypot(dx, dy))
            nx, ny = -dy / length, dx / length
            points = []
            for j in range(21):
                t = j / 20
                offset = bend * 4 * t * (1 - t)
                points.append((x0 + t * dx + offset * nx, y0 + t * dy + offset * ny))
            self.create_line(*[coord for point in points for coord in point],
                             fill=color, width=2 if open_line or not row else 3,
                             dash=(5, 5) if open_line else (), tags=(tag,))

            info = f"{line}   {start} → {end}\nLimit {limit:g} MW"
            if open_line:
                value = "OUT"
                info += "  ·  Out of service"
            elif row:
                mw = row["mw"]
                value = f"{abs(mw):.4g} MW"
                info += f"\nFlow {mw:+.4g} MW   ·   {row['loading']:.1f}% loaded"
                if abs(mw) > 1e-9:
                    self._arrow(points, mw > 0, node_radius, color, tag)
            else:
                value = ""
            self.hints[tag] = info
            labels.append((line, value, points, tag, color, open_line, overloaded))

        for line, value, points, tag, color, open_line, overloaded in labels:
            line_name = self._fit(line, max(36, width // 6), self.label_font)
            options = [f"{line_name}  ·  {value}", line_name] if value else [line_name]
            if len(labels) > 14:
                options = [line_name]
            pill_color = "#fceee9" if overloaded else "#f0f3f0" if open_line else "#ffffff"
            self._edge_label(points, tag, options, color, pill_color, occupied)

        for i, (bus, (x, y)) in enumerate(positions.items()):
            tag = f"bus_{i}"
            reference = bus == self.reference
            if reference:
                r = node_radius + 4
                self.create_oval(x-r, y-r, x+r, y+r, fill="#d7ede6", outline="", tags=(tag,))
            r = node_radius
            self.create_oval(x-r, y-r, x+r, y+r, fill=INK if reference else "#ffffff",
                             outline=INK, width=2, tags=(tag,))
            self.create_text(x, y, text=self._fit(bus, 2 * r - 3, self.node_font),
                             fill="#ffffff" if reference else INK, font=self.node_font, tags=(tag,))
            if reference:
                self.create_text(x, y-r-6, text="Reference", anchor="s",
                                 fill=MUTED, font=self.small_font, tags=(tag,))
            gen, demand = self.buses[bus]
            if reference and self.result:
                gen = self.result["slack_generation"]
            self.hints[tag] = f"Bus {bus}\nGeneration {gen:g} MW   ·   Demand {demand:g} MW"

    def _arrow(self, path, forward, radius, color, tag):
        # Place the arrow just before the receiving bus, clear of its outline.
        points = path if forward else path[::-1]
        end_x, end_y = points[-1]
        for a, b in zip(reversed(points[:-1]), reversed(points[1:])):
            dist = math.hypot(a[0] - end_x, a[1] - end_y)
            if dist >= radius + 10:
                angle = math.atan2(b[1] - a[1], b[0] - a[0])
                ux, uy = math.cos(angle), math.sin(angle)
                self.create_polygon(a[0], a[1], a[0]-8*ux+4*uy, a[1]-8*uy-4*ux,
                                    a[0]-8*ux-4*uy, a[1]-8*uy+4*ux,
                                    fill=color, outline="", tags=(tag,))
                return

    def _edge_label(self, points, tag, options, color, background, occupied):
        for label in options:
            w = self.label_font.measure(label) / 2 + 5
            h = self.label_font.metrics("linespace") / 2 + 1
            for i in (10, 8, 12, 7, 13):
                x, y = points[i]
                rect = (x-w, y-h, x+w, y+h)
                if rect[0] < 2 or rect[1] < 2 or rect[2] > self.winfo_width()-2 or rect[3] > self.winfo_height()-2:
                    continue
                if any(rect[0] < right and rect[2] > left and rect[1] < bottom and rect[3] > top
                       for left, top, right, bottom in occupied):
                    continue
                self.create_rectangle(*rect, fill=background, outline="#d8e2dd", tags=(tag,))
                self.create_text(x, y, text=label, fill=color, font=self.label_font, tags=(tag,))
                occupied.append(rect)
                return

    def _hover(self, event):
        self.delete("hint")
        items = self.find_overlapping(event.x - 3, event.y - 3, event.x + 3, event.y + 3)
        for item in reversed(items):
            tags = self.gettags(item)
            if not tags or tags[0] not in self.hints:
                continue
            width, height = self.winfo_width(), self.winfo_height()
            text = self.create_text(0, 0, text=self.hints[tags[0]], anchor="nw", justify="left",
                                    width=max(80, width-24), fill="#ffffff", font=self.small_font, tags=("hint",))
            left, top, right, bottom = self.bbox(text)
            x = max(8, min(event.x + 12, width - (right - left) - 8))
            y = event.y + 16
            if y + bottom - top + 8 > height:
                y = max(6, event.y - (bottom - top) - 14)
            self.move(text, x, y)
            left, top, right, bottom = self.bbox(text)
            box = self.create_rectangle(left-5, top-3, right+5, bottom+3,
                                        fill=INK, outline="", tags=("hint",))
            self.tag_lower(box, text)
            return
