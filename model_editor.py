"""Modal editor for a DC load-flow model. All edits are kept in a local draft."""
import tkinter as tk
from tkinter import messagebox, ttk

from grid_model import parse_model


PAPER = "#ffffff"
BACKGROUND = "#f6f8f6"
INK = "#20322e"
MUTED = "#536861"
TEAL = "#007d71"
EDGE = "#d9e2dc"
ERROR = "#a43128"
BODY = ("Segoe UI", 10)


def button(parent, label, command, primary=False):
    return tk.Button(
        parent, text=label, command=command, font=("Segoe UI", 10, "bold"),
        fg="white" if primary else INK, bg=TEAL if primary else PAPER,
        activeforeground="white" if primary else INK,
        activebackground="#006b60" if primary else "#e7f0eb",
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=TEAL if primary else EDGE, highlightcolor=TEAL,
        cursor="hand2", padx=14, pady=6,
    )


class DraftTable:
    """A fixed header above a vertically scrollable list of editable records."""

    def __init__(self, editor, parent, kind, headers, widths):
        self.editor = editor
        self.kind = kind
        self.widths = widths
        self.rows = []
        self.controls = {}
        self.frame = tk.Frame(parent, bg=PAPER)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)
        header = tk.Frame(self.frame, bg="#eaf1ed", padx=5)
        header.grid(row=0, column=0, sticky="ew")
        self._columns(header)
        for i, label in enumerate(headers):
            tk.Label(header, text=label, fg=MUTED, bg="#eaf1ed",
                     font=("Segoe UI", 9, "bold"), anchor="w").grid(
                         row=0, column=i, sticky="ew", padx=6, pady=8)
        self.canvas = tk.Canvas(self.frame, bg=PAPER, height=150, width=350,
                                highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body = tk.Frame(self.canvas, bg=PAPER, padx=5)
        self._columns(self.body)
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", lambda _: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(
            self.window, width=event.width))

    def _columns(self, widget):
        # Uniform column groups keep the header aligned with the entry widgets.
        for col, weight in enumerate(self.widths):
            widget.grid_columnconfigure(col, weight=weight, uniform="fields")
        widget.grid_columnconfigure(len(self.widths), minsize=72)

    def add(self, values, focus=False):
        variables = tuple(tk.StringVar(master=self.frame, value=value) for value in values)
        widgets = []
        row_number = len(self.rows)
        for col, var in enumerate(variables):
            if self.kind == "line" and col in (1, 2):
                field = ttk.Combobox(self.body, width=1, textvariable=var, state="readonly",
                                     values=self.editor.bus_ids(), font=BODY)
            else:
                field = tk.Entry(self.body, width=1, textvariable=var, font=BODY,
                                 fg=INK, bg=PAPER, relief="flat", bd=0,
                                 highlightthickness=1, highlightbackground=EDGE,
                                 highlightcolor=TEAL, insertbackground=TEAL)
                if self.kind == "bus" and col == 0:
                    field.previous_id = var.get()
                    field.bind("<FocusOut>", lambda _, f=field, v=var:
                               self.editor.rename_bus(f, v.get().strip()))
            field.grid(row=row_number, column=col, padx=5, pady=5, ipady=4, sticky="ew")
            field.bind("<FocusIn>", lambda _, w=field: self.reveal(w), add="+")
            widgets.append(field)
        remove = tk.Button(self.body, text="Remove", fg="#954438", bg=PAPER, bd=0,
                           activeforeground="#8b2e23", activebackground="#f8eae6",
                           relief="flat", font=("Segoe UI", 9), cursor="hand2",
                           command=lambda: self.editor.remove(self, variables))
        remove.grid(row=row_number, column=len(variables), sticky="ew", padx=4)
        self.rows.append(variables)
        self.controls[id(variables)] = [*widgets, remove]
        if focus:
            self.frame.update_idletasks()
            self.canvas.yview_moveto(1)
            widgets[0].focus_set()
            widgets[0].selection_range(0, "end")

    def reveal(self, widget):
        top = self.canvas.canvasy(0)
        area = self.canvas.winfo_height()
        full = self.body.winfo_height()
        y = widget.winfo_y()
        if full <= area:
            return
        if y < top:
            self.canvas.yview_moveto(max(0, y - 5) / full)
        elif y + widget.winfo_height() > top + area:
            self.canvas.yview_moveto((y + widget.winfo_height() + 5 - area) / full)

    def drop(self, variables):
        self.rows.remove(variables)
        for widget in self.controls.pop(id(variables)):
            widget.destroy()
        for i, row in enumerate(self.rows):
            for widget in self.controls[id(row)]:
                widget.grid_configure(row=i)

    def text(self):
        records = []
        for index, row in enumerate(self.rows, 1):
            fields = [var.get().strip() for var in row]
            if any(any(ch in value for ch in ",\r\n") for value in fields):
                raise ValueError(f"{self.kind.capitalize()} row {index} contains a comma or line break.")
            records.append(", ".join(fields))
        return "\n".join(records)


class ModelEditor(tk.Toplevel):
    def __init__(self, parent, buses, lines, reference, on_apply, *, line_id=None):
        super().__init__(parent)
        self.withdraw()
        self.title("Edit grid model")
        self.configure(bg=BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.on_apply = on_apply
        self.reference = tk.StringVar(master=self, value=reference)
        self.feedback = tk.StringVar(master=self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        top = tk.Frame(self, bg=BACKGROUND)
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 10))
        tk.Label(top, text="Edit grid model", fg=INK, bg=BACKGROUND,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self.reference_box = ttk.Combobox(top, textvariable=self.reference, state="readonly",
                                          width=10, font=BODY)
        self.reference_box.pack(side="right", padx=(7, 0))
        tk.Label(top, text="Reference bus", bg=BACKGROUND, fg=MUTED,
                 font=BODY).pack(side="right")
        self.tabs = tk.Frame(self, bg=BACKGROUND)
        self.tabs.grid(row=1, column=0, sticky="ew", padx=22)
        self.bus_tab = button(self.tabs, "Buses", lambda: self.show_table(self.bus_table))
        self.line_tab = button(self.tabs, "Lines", lambda: self.show_table(self.line_table))
        self.bus_tab.pack(side="left")
        self.line_tab.pack(side="left", padx=5)
        self.add_button = button(self.tabs, "Add bus", self.new_row)
        self.add_button.pack(side="right")
        holder = tk.Frame(self, bg=EDGE, padx=1, pady=1)
        holder.grid(row=2, column=0, sticky="nsew", padx=22, pady=10)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        self.bus_table = DraftTable(self, holder, "bus", ("Bus ID", "Generation (MW)", "Demand (MW)"),
                                    (2, 3, 3))
        self.line_table = DraftTable(self, holder, "line",
                                     ("Line ID", "From bus", "To bus", "Reactance (p.u.)", "Limit (MW)"),
                                     (4, 4, 4, 6, 5))
        for table in (self.bus_table, self.line_table):
            table.frame.grid(row=0, column=0, sticky="nsew")
        for bus_id, values in buses.items():
            self.bus_table.add((bus_id, *values))
        for name, values in lines.items():
            self.line_table.add((name, *values))
        self.update_bus_choices()
        footer = tk.Frame(self, bg=BACKGROUND)
        footer.grid(row=3, column=0, sticky="ew", padx=22, pady=(0, 16))
        footer.columnconfigure(0, weight=1)
        tk.Label(footer, textvariable=self.feedback, fg=ERROR, bg=BACKGROUND,
                 font=BODY, wraplength=370, anchor="w", justify="left").grid(
                     row=0, column=0, sticky="ew", padx=(0, 8))
        button(footer, "Cancel", self.destroy).grid(row=0, column=1, padx=8)
        button(footer, "Apply model", self.apply, primary=True).grid(row=0, column=2)
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Control-Return>", lambda _: self.apply())
        self.bind("<MouseWheel>", self.wheel)
        selected = next((row for row in self.line_table.rows if row[0].get() == line_id), None)
        self.show_table(self.line_table if line_id is not None else self.bus_table)
        self.minsize(640, 360)
        owner = parent.winfo_toplevel()
        owner.update_idletasks()
        width = min(840, self.winfo_screenwidth() - 32)
        height = min(525, self.winfo_screenheight() - 72)
        x = min(max(0, owner.winfo_rootx() + (owner.winfo_width() - width) // 2),
                max(0, self.winfo_screenwidth() - width))
        y = min(max(0, owner.winfo_rooty() + (owner.winfo_height() - height) // 2),
                max(0, self.winfo_screenheight() - height - 50))
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.grab_set()
        if selected is not None:
            field = self.line_table.controls[id(selected)][3]
            self.update_idletasks()
            self.line_table.reveal(field)
            field.focus_set()
            field.selection_range(0, "end")
        elif self.bus_table.rows:
            self.bus_table.controls[id(self.bus_table.rows[0])][0].focus_set()

    def wheel(self, event):
        pointer = self.winfo_containing(event.x_root, event.y_root)
        if pointer and str(pointer).startswith(str(self.active.frame)):
            self.active.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

    def show_table(self, table):
        self.active = table
        for candidate, tab in ((self.bus_table, self.bus_tab), (self.line_table, self.line_tab)):
            if candidate is table:
                candidate.frame.grid()
                tab.configure(bg="#d5ebe3", fg="#005f54", highlightbackground="#96cabe")
            else:
                candidate.frame.grid_remove()
                tab.configure(bg=PAPER, fg=INK, highlightbackground=EDGE)
        self.add_button.configure(text="Add bus" if table is self.bus_table else "Add line")
        self.update_counts()

    def update_counts(self):
        self.bus_tab.configure(text=f"Buses ({len(self.bus_table.rows)})")
        self.line_tab.configure(text=f"Lines ({len(self.line_table.rows)})")

    def bus_ids(self):
        return [row[0].get().strip() for row in self.bus_table.rows if row[0].get().strip()]

    def update_bus_choices(self):
        choices = self.bus_ids()
        self.reference_box.configure(values=choices)
        for row in self.line_table.rows:
            for widget in self.line_table.controls[id(row)][1:3]:
                widget.configure(values=choices)

    def rename_bus(self, field, new_id):
        previous = field.previous_id
        if not new_id or previous == new_id or self.bus_ids().count(new_id) != 1:
            return
        if previous and previous not in self.bus_ids():
            for row in self.line_table.rows:
                for endpoint in row[1:3]:
                    if endpoint.get() == previous:
                        endpoint.set(new_id)
            if self.reference.get() == previous:
                self.reference.set(new_id)
        field.previous_id = new_id
        self.update_bus_choices()

    def new_row(self):
        table = self.active
        if table is self.bus_table and len(table.rows) >= 10:
            self.feedback.set("A grid supports up to 10 buses.")
            return
        prefix = "B" if table is self.bus_table else "L"
        used = {row[0].get().strip() for row in table.rows}
        i = 1
        while f"{prefix}{i}" in used:
            i += 1
        new_id = f"{prefix}{i}"
        if table is self.bus_table:
            table.add((new_id, 0, 0), focus=True)
            self.update_bus_choices()
        else:
            endpoints = (self.bus_ids() + ["", ""])[:2]
            table.add((new_id, *endpoints, "0.10", 100), focus=True)
        self.feedback.set("")
        self.update_counts()

    def remove(self, table, row):
        if table is self.bus_table:
            name = row[0].get().strip()
            attached = [line for line in self.line_table.rows
                        if name in (line[1].get(), line[2].get())]
            if attached:
                if not messagebox.askyesno("Remove bus and lines",
                                           f"Remove bus {name} and its {len(attached)} connected "
                                           "line(s) from this draft?", parent=self):
                    return
                for line in attached:
                    self.line_table.drop(line)
            table.drop(row)
            self.update_bus_choices()
            if self.reference.get() == name:
                choices = self.bus_ids()
                self.reference.set(choices[0] if choices else "")
        else:
            table.drop(row)
        self.update_counts()
        self.feedback.set("")

    def apply(self):
        # A mouse click on a Windows button can leave focus in the edited ID.
        for row in self.bus_table.rows:
            field = self.bus_table.controls[id(row)][0]
            self.rename_bus(field, row[0].get().strip())
        try:
            bus_text = self.bus_table.text()
            line_text = self.line_table.text()
            reference = self.reference.get()
            buses, lines = parse_model(bus_text, line_text, reference)
        except ValueError as error:
            self.feedback.set(str(error))
            return
        self.on_apply(buses, lines, reference)
        self.destroy()


def edit_model(parent, buses, lines, reference, on_apply, *, line_id=None):
    """Open a grid draft, optionally at the reactance of a specific line."""
    return ModelEditor(parent, buses, lines, reference, on_apply, line_id=line_id)
