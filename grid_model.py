"""DC load-flow model and SQLite persistence."""
import json
import math
import sqlite3
from contextlib import closing

BASE_MVA = 100
SAMPLE_BUSES = """A, 100, 0
B, 0, 30
C, 0, 20
D, 0, 25
E, 0, 25"""
SAMPLE_LINES = """L1, A, B, 0.10, 75
L2, B, C, 0.10, 60
L3, C, D, 0.10, 60
L4, D, E, 0.10, 60
L5, E, A, 0.10, 75"""


def parse_model(bus_text, line_text, reference):
    buses = {}
    lines = {}

    def rows(source, size, label):
        for number, row in enumerate(source.splitlines(), 1):
            if row.strip():
                fields = [field.strip() for field in row.split(",")]
                if len(fields) != size or not all(fields):
                    raise ValueError(f"{label} row {number} needs {size} comma-separated values.")
                yield fields

    def number(value, label, positive=False):
        try:
            result = float(value)
        except ValueError:
            raise ValueError(f"{label} must be numeric.") from None
        if not math.isfinite(result) or result < 0 or (positive and result == 0):
            raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}.")
        return result

    for bus, gen, demand in rows(bus_text, 3, "Bus"):
        if bus in buses:
            raise ValueError(f"Duplicate bus ID {bus}.")
        buses[bus] = (number(gen, f"{bus} generation"), number(demand, f"{bus} demand"))
    if not 5 <= len(buses) <= 10:
        raise ValueError("Enter 5 to 10 buses.")
    if reference not in buses:
        raise ValueError("The reference bus must be an existing bus ID.")

    for line, start, end, x, limit in rows(line_text, 5, "Line"):
        if line in lines:
            raise ValueError(f"Duplicate line ID {line}.")
        if start not in buses or end not in buses or start == end:
            raise ValueError(f"Line {line} needs two distinct, existing buses.")
        lines[line] = (start, end, number(x, f"{line} reactance", True),
                       number(limit, f"{line} limit", True))
    return buses, lines


def invert(matrix):
    """Gauss–Jordan inversion with partial pivoting."""
    size = len(matrix)
    augmented = [list(row) + [float(i == j) for j in range(size)]
                 for i, row in enumerate(matrix)]
    scale = max(abs(value) for row in matrix for value in row)
    for column in range(size):
        pivot = max(range(column, size), key=lambda i: abs(augmented[i][column]))
        if abs(augmented[pivot][column]) <= 1e-12 * scale:
            raise ValueError("The reduced matrix is numerically singular. Check the reactances.")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for i, row in enumerate(augmented):
            if i != column:
                factor = row[column]
                augmented[i] = [a - factor * b for a, b in zip(row, augmented[column])]
    return [row[size:] for row in augmented]


def solve(buses, lines, reference, outage=None):
    if outage is not None and outage not in lines:
        raise ValueError("Choose an existing line ID for the outage.")
    ids = list(buses)
    index = {bus: i for i, bus in enumerate(ids)}
    adjacency = {bus: [] for bus in buses}
    matrix = [[0.0 for _ in ids] for _ in ids]
    for line, (start, end, x, _) in lines.items():
        if line == outage:
            continue
        adjacency[start].append(end)
        adjacency[end].append(start)
        i, j = index[start], index[end]
        weight = 1 / x
        matrix[i][i] += weight
        matrix[j][j] += weight
        matrix[i][j] -= weight
        matrix[j][i] -= weight

    visited = {reference}
    pending = [reference]
    while pending:
        for neighbor in adjacency[pending.pop()]:
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    unreachable = [bus for bus in ids if bus not in visited]
    if unreachable:
        raise ValueError("Grid is disconnected. Buses outside the reference island: "
                         + ", ".join(unreachable))

    indices = [i for i, bus in enumerate(ids) if bus != reference]
    reduced = [[matrix[i][j] for j in indices] for i in indices]
    if any(not math.isfinite(value) for row in reduced for value in row):
        raise ValueError("Reactances produce values outside the supported numeric range.")
    inverse = invert(reduced)
    net = [(buses[ids[i]][0] - buses[ids[i]][1]) / BASE_MVA for i in indices]
    angles = {reference: 0.0}
    angles.update((ids[i], math.fsum(a * b for a, b in zip(row, net)))
                  for i, row in zip(indices, inverse))
    slack_generation = buses[reference][1] - BASE_MVA * math.fsum(net)
    if slack_generation < -1e-8:
        raise ValueError("The reference bus would need negative generation. Adjust generation or demand.")
    slack_generation = max(0.0, slack_generation)
    flows = []
    for line, (start, end, x, limit) in lines.items():
        mw = 0.0 if line == outage else (angles[start] - angles[end]) * BASE_MVA / x
        loading = abs(mw) / limit * 100
        if not math.isfinite(loading):
            raise ValueError("Line loading exceeds the supported numeric range.")
        flows.append(dict(line=line, start=start, end=end, mw=mw, limit=limit, loading=loading,
                          state="OUT" if line == outage else
                          "OVERLOAD" if loading > 100 + 1e-8 else "OK"))
    flows.sort(key=lambda row: (row["state"] == "OUT", -row["loading"], row["line"]))
    return dict(ids=ids, matrix=matrix, reduced=reduced, inverse=inverse, angles=angles,
                slack_generation=slack_generation, flows=flows)


class RunStore:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS demand_scenarios (
                    id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    reference_bus TEXT NOT NULL, outage TEXT, case_type TEXT NOT NULL,
                    error TEXT, result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS buses (
                    scenario_id INTEGER REFERENCES demand_scenarios(id),
                    bus_id TEXT, generation_mw REAL, demand_mw REAL,
                    PRIMARY KEY (scenario_id, bus_id)
                );
                CREATE TABLE IF NOT EXISTS lines (
                    scenario_id INTEGER REFERENCES demand_scenarios(id),
                    line_id TEXT, start_bus TEXT, end_bus TEXT, reactance_pu REAL, limit_mw REAL,
                    PRIMARY KEY (scenario_id, line_id)
                );
                CREATE TABLE IF NOT EXISTS line_flows (
                    scenario_id INTEGER, line_id TEXT, flow_mw REAL, loading_pct REAL, status TEXT,
                    PRIMARY KEY (scenario_id, line_id),
                    FOREIGN KEY (scenario_id, line_id) REFERENCES lines(scenario_id, line_id)
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def save(self, buses, lines, reference, runs):
        saved = []
        with closing(self.connect()) as db, db:
            for outage, result, error in runs:
                kind = "Base" if outage is None else "Outage"
                cursor = db.execute(
                    """INSERT INTO demand_scenarios
                       (reference_bus, outage, case_type, error, result_json) VALUES (?, ?, ?, ?, ?)""",
                    (reference, outage, kind, error, json.dumps(result) if result else None))
                run_id = cursor.lastrowid
                db.executemany("INSERT INTO buses VALUES (?, ?, ?, ?)",
                               [(run_id, bus, *values) for bus, values in buses.items()])
                db.executemany("INSERT INTO lines VALUES (?, ?, ?, ?, ?, ?)",
                               [(run_id, line, *values) for line, values in lines.items()])
                if result:
                    db.executemany("INSERT INTO line_flows VALUES (?, ?, ?, ?, ?)",
                                   [(run_id, r["line"], r["mw"], r["loading"], r["state"])
                                    for r in result["flows"]])
                saved.append(run_id)
        return saved

    def history(self):
        with closing(self.connect()) as db:
            return db.execute("""SELECT id, case_type, outage, error FROM demand_scenarios
                                 ORDER BY id DESC""").fetchall()

    def load(self, run_id):
        with closing(self.connect()) as db:
            reference, outage, error, result = db.execute(
                "SELECT reference_bus, outage, error, result_json FROM demand_scenarios WHERE id = ?",
                (run_id,)).fetchone()
            buses = db.execute("""SELECT bus_id, generation_mw, demand_mw FROM buses
                                  WHERE scenario_id = ? ORDER BY rowid""", (run_id,)).fetchall()
            lines = db.execute("""SELECT line_id, start_bus, end_bus, reactance_pu, limit_mw FROM lines
                                  WHERE scenario_id = ? ORDER BY rowid""", (run_id,)).fetchall()
        return buses, lines, reference, outage, error, json.loads(result) if result else None
