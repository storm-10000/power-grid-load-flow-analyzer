"""Power Grid Load-Flow Analyzer desktop interface. Run with python app.py."""
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from grid_model import RunStore, SAMPLE_BUSES, SAMPLE_LINES, parse_model, solve
from model_editor import edit_model
from network_view import NetworkView


BG = "#f2f5f3"
WHITE = "#ffffff"
INK = "#162e30"
MUTED = "#50676a"
BORDER = "#d4e0dd"
TEAL = "#007d71"
NAV = "#133637"
PALE = "#e3f2ee"
RED = "#b64336"
PINK = "#fbece8"
FAMILY = "Segoe UI"


def label(parent, text, *, size=10, color=INK, bold=False, **options):
    return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                    font=(FAMILY, size, "bold" if bold else "normal"),
                    anchor="w", borderwidth=0, **options)


def card(parent):
    return tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=BORDER)


def button(parent, title, action, style="Light.TButton"):
    return ttk.Button(parent, text=title, command=action, style=style, cursor="hand2")


def number(value, digits=2):
    return f"{value:,.{digits}f}".rstrip("0").rstrip(".") or "0"


def signed(value):
    return f"{value:+.2f}" if abs(value) >= 0.005 else "0.00"


def setup_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    for name, bg, fg, hover in (("Light.TButton", WHITE, INK, "#edf3f0"),
                                ("Accent.TButton", TEAL, WHITE, "#00675d")):
        edge = BORDER if bg == WHITE else TEAL
        style.configure(name, background=bg, foreground=fg, bordercolor=edge, lightcolor=bg,
                        darkcolor=bg, focuscolor=fg, font=(FAMILY, 10, "bold"),
                        padding=(13, 7), relief="solid", borderwidth=1)
        style.map(name, background=[("active", hover)], foreground=[("disabled", MUTED)],
                  bordercolor=[("focus", "#429e92"), ("active", edge)])
    style.configure("Grid.Treeview", background=WHITE, fieldbackground=WHITE,
                    foreground=INK, font=(FAMILY, 10), rowheight=29, borderwidth=0)
    style.configure("Grid.Treeview.Heading", background="#eef4f1", foreground=MUTED,
                    font=(FAMILY, 9, "bold"), relief="flat", padding=(8, 6))
    style.map("Grid.Treeview", background=[("selected", "#c9e5df")],
              foreground=[("selected", INK)])
    style.configure("TCombobox", arrowsize=14, padding=(8, 5), bordercolor=BORDER,
                    foreground=INK, fieldbackground=WHITE)
    style.map("TCombobox", fieldbackground=[("readonly", WHITE)],
              selectbackground=[("readonly", WHITE)], selectforeground=[("readonly", INK)])


def table(parent, columns, height):
    """Create a horizontally scrollable table; columns are (key, title, width, anchor)."""
    holder = tk.Frame(parent, bg=WHITE)
    holder.pack(fill="both", expand=True)
    view = ttk.Treeview(holder, show="headings", columns=[c[0] for c in columns],
                        height=height, style="Grid.Treeview", selectmode="browse")
    for key, title, width, anchor in columns:
        view.column(key, width=width, minwidth=min(width, 62), anchor=anchor)
        view.heading(key, text=title, anchor=anchor)
    view.tag_configure("stripe", background="#f7faf8")
    view.tag_configure("OVERLOAD", background=PINK, foreground="#8d342a")
    view.tag_configure("OUT", background="#edf0f0", foreground="#57686c")
    vertical = ttk.Scrollbar(holder, orient="vertical", command=view.yview)
    horizontal = ttk.Scrollbar(holder, orient="horizontal", command=view.xview)

    def scroll_bar(bar, first, last):
        if float(first) <= 0 and float(last) >= 1:
            bar.grid_remove()
        else:
            bar.grid()
        bar.set(first, last)

    view.configure(yscrollcommand=lambda a, b: scroll_bar(vertical, a, b),
                   xscrollcommand=lambda a, b: scroll_bar(horizontal, a, b))
    holder.columnconfigure(0, weight=1)
    holder.rowconfigure(0, weight=1)
    view.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    return view


def metric_symbol(parent, kind, color):
    canvas = tk.Canvas(parent, width=24, height=24, bg=parent.cget("bg"),
                       highlightthickness=0)
    if kind == "demand":
        canvas.create_line(2, 14, 7, 14, 10, 5, 14, 20, 17, 11, 22, 11,
                           width=2, fill=color, joinstyle="round")
    elif kind == "lines":
        canvas.create_line(4, 18, 18, 5, fill=color, width=2)
        for x, y in [(4, 18), (18, 5)]:
            canvas.create_rectangle(x-2, y-2, x+2, y+2, width=2, outline=color, fill=WHITE)
    elif kind == "peak":
        for x, top in [(4, 15), (10, 10), (16, 4)]:
            canvas.create_rectangle(x, top, x+3, 20, fill=color, outline="")
    else:
        canvas.create_polygon(12, 3, 22, 20, 2, 20, outline=color, fill="", width=2)
        canvas.create_line(12, 9, 12, 14, fill=color, width=2)
        canvas.create_oval(11, 16, 13, 18, fill=color, outline="")
    return canvas


class GridApp:
    def __init__(self, root, store):
        self.root = root
        self.store = store
        self.buses, self.lines = parse_model(SAMPLE_BUSES, SAMPLE_LINES, "A")
        self.reference = "A"
        self.outage = tk.StringVar(root, "L1")
        self.active_outage = None
        self.base = solve(self.buses, self.lines, self.reference)
        self.contingency = None
        self.problem = ""
        self.page = "Overview"
        self.matrix_case = tk.StringVar(root)
        self.matrix_kind = tk.StringVar(root, "Full susceptance B")
        self.status = tk.StringVar(root, "Sample grid loaded · Base case preview")
        root.title("Gridflow | Power Grid Load-Flow Analyzer")
        root.configure(bg=BG)
        root.geometry(f"{min(1220, root.winfo_screenwidth()-60)}x{min(830, root.winfo_screenheight()-90)}")
        root.minsize(850, 550)
        setup_theme(root)
        self.build_shell()
        self.show_page("Overview")

    def build_shell(self):
        header = tk.Frame(self.root, bg=NAV, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        mark = tk.Canvas(header, bg=NAV, width=34, height=33, highlightthickness=0)
        mark.pack(side="left", padx=(22, 8))
        mark.create_line(5, 20, 17, 8, 28, 17, 15, 26, 5, 20, fill="#80dbc0", width=2)
        for x, y in [(5, 20), (17, 8), (28, 17), (15, 26)]:
            mark.create_rectangle(x-2, y-2, x+2, y+2, fill="#c9f4df", outline="")
        label(header, "Gridflow", size=16, color=WHITE, bold=True).pack(side="left", padx=(0, 28))
        self.navigation = {}
        for name in ("Overview", "Matrices & angles", "Saved runs"):
            nav = tk.Button(header, text=name, command=lambda dest=name: self.show_page(dest),
                            font=(FAMILY, 10, "bold"), relief="flat", bd=0, padx=16, pady=6,
                            highlightthickness=1, highlightbackground=NAV, cursor="hand2",
                            activebackground="#345655", activeforeground=WHITE)
            nav.pack(side="left", padx=2)
            self.navigation[name] = nav
        label(header, "DC load flow   /   100 MVA", size=10, color="#b5cec7").pack(side="right", padx=24)

        footer = tk.Frame(self.root, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        footer.pack(side="bottom", fill="x")
        status = label(footer, "", size=9, color=MUTED, textvariable=self.status, wraplength=780)
        status.pack(anchor="w", padx=20, pady=5)
        holder = tk.Frame(self.root, bg=BG)
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, bg=BG, highlightthickness=0, width=1, height=1)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        def update_scrollbar(first, last):
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.grid_remove()
            else:
                scrollbar.grid()
            scrollbar.set(first, last)
        self.canvas.configure(yscrollcommand=update_scrollbar)
        self.content = tk.Frame(self.canvas, bg=BG, padx=22, pady=16)
        window = self.canvas.create_window(0, 0, anchor="nw", window=self.content)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.content.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.root.bind("<MouseWheel>", self.wheel, add=True)

    def wheel(self, event):
        if event.widget.winfo_toplevel() != self.root:
            return
        if isinstance(event.widget, ttk.Treeview) and event.widget.yview() != (0.0, 1.0):
            return
        if isinstance(event.widget, ttk.Combobox):
            return
        self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def show_page(self, page):
        self.page = page
        for child in self.content.winfo_children():
            child.destroy()
        for name, nav in self.navigation.items():
            nav.configure(bg="#305857" if name == page else NAV,
                          fg=WHITE if name == page else "#b9d2cb")
        if page == "Overview":
            self.overview()
        elif page == "Matrices & angles":
            self.matrix_page()
        else:
            self.history_page()
        self.canvas.yview_moveto(0)

    def heading(self, title, subtitle):
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill="x", pady=(0, 13))
        text = tk.Frame(row, bg=BG)
        text.pack(side="left")
        label(text, title, size=23, bold=True).pack(anchor="w")
        label(text, subtitle, color=MUTED).pack(anchor="w")
        return row

    def overview(self):
        heading = self.heading("Load-flow overview",
                               f"{len(self.buses)} buses  ·  {len(self.lines)} transmission lines  ·  Reference bus {self.reference}")
        button(heading, "Edit grid", lambda: edit_model(self.root, self.buses, self.lines,
                                                        self.reference, self.apply_grid)).pack(side="right")
        button(heading, "Load sample", self.sample).pack(side="right", padx=(0, 7))
        result = self.contingency if self.active_outage else self.base
        flows = result["flows"] if result else []
        worst = max((row["loading"] for row in flows), default=0)
        overloaded = sum(row["state"] == "OVERLOAD" for row in flows)
        metrics = tk.Frame(self.content, bg=BG)
        metrics.pack(fill="x", pady=(0, 12))
        summary = [
            ("Total demand", number(sum(d for _, d in self.buses.values())), "MW", "demand", TEAL),
            ("Active lines", str(len(self.lines) - int(bool(self.active_outage))), f"/ {len(self.lines)}", "lines", TEAL),
            ("Peak loading", number(worst) if result else "—", "%" if result else "", "peak", RED if overloaded else TEAL),
            ("Overloaded lines", str(overloaded) if result else "—", "", "overload", RED if overloaded else TEAL),
        ]
        for i, (title, value, unit, kind, color) in enumerate(summary):
            metrics.columnconfigure(i, weight=1, uniform="metrics")
            box = card(metrics)
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))
            body = tk.Frame(box, bg=WHITE, padx=13, pady=7)
            body.pack(fill="x")
            label(body, title, size=10, color=MUTED).grid(row=0, column=0, sticky="w", columnspan=2)
            metric_symbol(body, kind, color).grid(row=0, column=2, rowspan=2, sticky="e")
            value_row = tk.Frame(body, bg=WHITE)
            value_row.grid(row=1, column=0, columnspan=2, sticky="w")
            label(value_row, value, size=20, bold=True, color=RED if color == RED else INK).pack(side="left")
            label(value_row, unit, color=MUTED).pack(side="left", padx=4, anchor="s", pady=(0, 4))
            body.columnconfigure(1, weight=1)

        middle = tk.Frame(self.content, bg=BG)
        middle.pack(fill="x", pady=(0, 12))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, minsize=265)
        map_card = card(middle)
        map_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        map_head = tk.Frame(map_card, bg=WHITE)
        map_head.pack(fill="x", padx=14, pady=(9, 7))
        label(map_head, "Network topology", size=13, bold=True).pack(side="left")
        case = f"{self.active_outage} outage" if self.active_outage else "Base case" if self.base else "Grid model"
        chip = label(map_head, case, size=9, color=TEAL, bold=True, padx=8, pady=2)
        chip.configure(bg=PALE)
        chip.pack(side="right")
        self.network = NetworkView(map_card, height=206, width=1)
        self.network.pack(fill="both", expand=True)
        self.network.show(self.buses, self.lines, self.reference, result, self.active_outage)
        legend = tk.Frame(map_card, bg=WHITE)
        legend.pack(fill="x", padx=14, pady=5)
        for caption, color, sample in (("Flow", TEAL, "━"), ("Overload", RED, "━"), ("Out of service", MUTED, "┄")):
            label(legend, sample, color=color, bold=True).pack(side="left")
            label(legend, caption, size=9, color=MUTED).pack(side="left", padx=(4, 13))

        controls = card(middle)
        controls.grid(row=0, column=1, sticky="nsew")
        panel = tk.Frame(controls, bg=WHITE, padx=15, pady=11)
        panel.pack(fill="both", expand=True)
        label(panel, "Scenario controls", size=13, bold=True).pack(anchor="w")
        label(panel, "Line to remove", size=10, color=MUTED).pack(anchor="w", pady=(16, 3))
        self.outage_picker = ttk.Combobox(panel, state="readonly", textvariable=self.outage,
                                          values=list(self.lines), width=24, font=(FAMILY, 10))
        self.outage_picker.pack(fill="x")
        self.outage_picker.bind("<MouseWheel>", lambda _: "break")
        detail = label(panel, "", size=9, color=MUTED)
        detail.pack(anchor="w", pady=(4, 10))
        def selected_line(_event=None):
            line = self.lines.get(self.outage.get())
            if line:
                start, end, _, limit = line
                detail.configure(text=f"{start} → {end}  ·  {number(limit)} MW limit")
            else:
                detail.configure(text="Add a transmission line to run an outage.")
        self.outage_picker.bind("<<ComboboxSelected>>", selected_line)
        selected_line()
        button(panel, "Compare outage", lambda: self.run(True), "Accent.TButton").pack(fill="x", pady=(5, 7))
        button(panel, "Run base case", self.run).pack(fill="x")

        flow_card = card(self.content)
        flow_card.pack(fill="x")
        head = tk.Frame(flow_card, bg=WHITE)
        head.pack(fill="x", padx=14, pady=(9, 3))
        label(head, "Line flows", size=13, bold=True).pack(side="left")
        button(head, "Edit lines", self.edit_lines).pack(side="right")
        label(head, "Highest loading first" if result else "Model order", size=9, color=MUTED).pack(side="right", padx=12)
        if self.problem:
            alert = label(flow_card, self.problem, size=10, color="#902e23", wraplength=740,
                          justify="left", padx=12, pady=5)
            alert.configure(bg=PINK)
            alert.pack(fill="x", padx=10, pady=3)
        explanation = "Signed MW follows the listed route. A negative value means reverse flow."
        label(flow_card, explanation, size=9, color=MUTED).pack(anchor="w", padx=14, pady=(0, 7))
        self.flow_table(flow_card, result)

    def flow_table(self, parent, result):
        columns = [("line", "Line", 95, "w"), ("route", "Route", 140, "w"),
                   ("base", "Base (MW)", 110, "e")]
        if self.active_outage:
            columns.append(("outage", "Outage (MW)", 115, "e"))
        columns.extend([("limit", "Limit (MW)", 110, "e"), ("load", "Loading", 105, "e"),
                        ("state", "Status", 130, "center")])
        self.flows = table(parent, columns, height=min(7, max(3, len(self.lines))))
        base_mw = {r["line"]: r["mw"] for r in self.base["flows"]} if self.base else {}
        order = [r["line"] for r in result["flows"]] if result else list(self.lines)
        rows = {r["line"]: r for r in result["flows"]} if result else {}
        for i, line in enumerate(order):
            start, end, _, limit = self.lines[line]
            row = rows.get(line)
            state = row["state"] if row else "OUT" if line == self.active_outage else "UNSOLVED"
            values = [line, f"{start}  →  {end}", signed(base_mw[line]) if line in base_mw else "—"]
            if self.active_outage:
                values.append(signed(row["mw"]) if row else "—")
            values.extend([number(limit), f"{number(row['loading'])}%" if row else "—",
                           {"OK": "Within limit", "OVERLOAD": "Overload", "OUT": "Out of service",
                            "UNSOLVED": "Unsolved"}[state]])
            tag = state if state in ("OVERLOAD", "OUT") else "stripe" if i % 2 else ""
            self.flows.insert("", "end", values=values, tags=(tag,))
        self.flows.bind("<Double-Button-1>", self.open_line_at_pointer)
        self.flows.bind("<Return>", lambda _: self.edit_lines())

    def open_line_at_pointer(self, event):
        row = self.flows.identify_row(event.y)
        if row and self.flows.identify_region(event.x, event.y) in ("cell", "tree"):
            self.flows.selection_set(row)
            self.edit_lines()
            return "break"

    def edit_lines(self):
        selected = self.flows.selection()
        line_id = self.flows.set(selected[0], "line") if selected else next(iter(self.lines), "")
        return edit_model(self.root, self.buses, self.lines, self.reference,
                          self.apply_grid, line_id=line_id)

    def run(self, compare=False):
        outage = self.outage.get() if compare else None
        if compare and outage not in self.lines:
            messagebox.showinfo("Choose a line", "Select a transmission line to remove.", parent=self.root)
            return
        try:
            base = solve(self.buses, self.lines, self.reference)
            runs = [(None, base, None)]
            result, error = None, ""
            if compare:
                try:
                    result = solve(self.buses, self.lines, self.reference, outage)
                except (ValueError, ArithmeticError) as exc:
                    error = str(exc)
                runs.append((outage, result, error or None))
            saved = self.store.save(self.buses, self.lines, self.reference, runs)
        except (ValueError, ArithmeticError, sqlite3.Error) as exc:
            messagebox.showerror("Cannot complete run", str(exc), parent=self.root)
            return
        self.base, self.contingency, self.active_outage, self.problem = base, result, outage, error
        self.matrix_case.set("Outage" if result else "Base case")
        self.status.set(f"{'Comparison' if compare else 'Base case'} saved  ·  "
                        + ", ".join(f"Run #{run_id}" for run_id in saved))
        self.show_page("Overview")

    def apply_grid(self, buses, lines, reference):
        self.buses, self.lines, self.reference = buses, lines, reference
        if self.outage.get() not in lines:
            self.outage.set(next(iter(lines), ""))
        self.active_outage, self.contingency, self.problem = None, None, ""
        try:
            self.base = solve(buses, lines, reference)
        except (ValueError, ArithmeticError) as exc:
            self.base, self.problem = None, str(exc)
        self.matrix_case.set("Base case")
        self.status.set("Working grid updated · Base case preview" if self.base else "Working grid updated · Unsolved")
        self.show_page("Overview")

    def sample(self):
        buses, lines = parse_model(SAMPLE_BUSES, SAMPLE_LINES, "A")
        if (self.buses, self.lines, self.reference) != (buses, lines, "A"):
            if not messagebox.askyesno("Load sample grid", "Replace the working grid with the five-bus sample?",
                                       parent=self.root):
                return
        self.outage.set("L1")
        self.apply_grid(buses, lines, "A")
        self.status.set("Sample grid loaded · Base case preview")

    def matrix_page(self):
        self.heading("Matrices & angles", f"DC solution on a 100 MVA base  ·  Reference bus {self.reference}")
        frame = card(self.content)
        frame.pack(fill="x")
        control = tk.Frame(frame, bg=WHITE, padx=12, pady=10)
        control.pack(fill="x")
        cases = ["Base case"] + (["Outage"] if self.active_outage else [])
        if self.matrix_case.get() not in cases:
            self.matrix_case.set("Base case")
        for title, variable, options in (
            ("Scenario", self.matrix_case, cases),
            ("Matrix", self.matrix_kind, ["Full susceptance B", "Reduced B", "Inverse of reduced B"]),
        ):
            label(control, title, color=MUTED).pack(side="left", padx=(0, 6))
            pick = ttk.Combobox(control, state="readonly", values=options, width=max(map(len, options))+1,
                                textvariable=variable)
            pick.pack(side="left", padx=(0, 18))
            pick.bind("<<ComboboxSelected>>", lambda _: self.show_page("Matrices & angles"))
            pick.bind("<MouseWheel>", lambda _: "break")
        result = self.contingency if self.matrix_case.get() == "Outage" else self.base
        if not result:
            label(frame, self.problem or "Run the base case to view a solution.", color=RED,
                  wraplength=740).pack(anchor="w", padx=14, pady=14)
            return
        ids = result["ids"]
        kind = self.matrix_kind.get()
        key = {"Full susceptance B": "matrix", "Reduced B": "reduced", "Inverse of reduced B": "inverse"}[kind]
        names = ids if key == "matrix" else [bus for bus in ids if bus != self.reference]
        matrix = table(frame, [("bus", "Bus", 82, "w")] +
                       [(str(i), name, 75, "e") for i, name in enumerate(names)], len(names))
        for i, (name, row) in enumerate(zip(names, result[key])):
            matrix.insert("", "end", values=[name] + [f"{value:.5g}" for value in row],
                          tags=("stripe",) if i % 2 else ())
        angles = card(self.content)
        angles.pack(fill="x", pady=(12, 0))
        label(angles, "Bus angles & dispatch", size=13, bold=True).pack(anchor="w", padx=14, pady=9)
        grid = table(angles, [("bus", "Bus", 120, "w"), ("angle", "Angle (rad)", 140, "e"),
                              ("gen", "Generation (MW)", 140, "e"), ("demand", "Demand (MW)", 140, "e"),
                              ("role", "Bus role", 150, "center")], len(ids))
        for i, bus in enumerate(ids):
            generation, demand = self.buses[bus]
            if bus == self.reference:
                generation = result["slack_generation"]
            grid.insert("", "end", values=(bus, f"{result['angles'][bus]:.6f}", number(generation),
                        number(demand), "Reference" if bus == self.reference else "Non-reference"),
                        tags=("stripe",) if i % 2 else ())

    def history_page(self):
        self.heading("Saved runs", "Open a stored scenario to inspect its grid, flows, and matrices.")
        box = card(self.content)
        box.pack(fill="x")
        records = self.store.history()
        if not records:
            label(box, "No saved runs yet", size=14, bold=True).pack(anchor="w", padx=16, pady=(16, 4))
            label(box, "Run a base case or compare an outage to save a scenario.",
                  color=MUTED).pack(anchor="w", padx=16, pady=(0, 15))
            return
        head = tk.Frame(box, bg=WHITE, padx=12, pady=8)
        head.pack(fill="x")
        label(head, f"{len(records)} saved scenarios", size=13, bold=True).pack(side="left")
        button(head, "Open selected run", self.open_run).pack(side="right")
        self.history = table(box, [("id", "Run", 100, "w"), ("case", "Scenario", 160, "w"),
                                   ("out", "Removed line", 120, "w"), ("status", "Solution", 160, "w")],
                             min(len(records), 14))
        for i, (run_id, case, outage, error) in enumerate(records):
            self.history.insert("", "end", iid=str(run_id), values=(f"#{run_id}",
                                "Base case" if case == "Base" else "Line outage", outage or "—",
                                "Unsolved" if error else "Solved"), tags=("stripe",) if i % 2 else ())
        self.history.selection_set(str(records[0][0]))
        self.history.bind("<Double-Button-1>", lambda _: self.open_run())
        self.history.bind("<Return>", lambda _: self.open_run())

    def open_run(self):
        selection = self.history.selection()
        if not selection:
            return
        run_id = int(selection[0])
        bus_rows, line_rows, reference, outage, error, result = self.store.load(run_id)
        buses = {bus: (gen, demand) for bus, gen, demand in bus_rows}
        lines = {line: (a, b, x, limit) for line, a, b, x, limit in line_rows}
        self.buses, self.lines, self.reference = buses, lines, reference
        self.outage.set(outage or next(iter(lines), ""))
        self.active_outage, self.problem = outage, error or ""
        self.base = solve(buses, lines, reference) if outage else result
        self.contingency = result if outage else None
        self.matrix_case.set("Outage" if outage and result else "Base case")
        self.status.set(f"Opened saved run #{run_id}")
        self.show_page("Overview")


def main():
    root = tk.Tk()
    GridApp(root, RunStore(Path(__file__).with_name("grid_runs.sqlite3")))
    root.mainloop()


if __name__ == "__main__":
    main()
