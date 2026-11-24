# Power Grid Load-Flow Analyzer

Project 24 · Four-person group project

## Run in a browser

Open the deployed Netlify homepage to solve the sample grid, compare a line
outage, edit the model, and inspect matrices and bus angles. The browser
analyzer runs locally in the page; reloading restores the sample. Use the
desktop edition if you need to save and reopen runs.

To preview the static site locally with Python, run
`python -m http.server 8889 --directory web` and open `http://localhost:8889`.

## Run the desktop edition

Extract the ZIP to a writable folder. On Windows, double-click **Open Gridflow.cmd**.
You can also run `python app.py` from that folder. Use Python 3.10 or newer with
Tkinter. The app uses the Python standard library and stores saved runs in
`grid_runs.sqlite3` beside the app.

## Demonstrate the sample grid (desktop)

1. Open **Overview**. The five-bus sample opens with a solved base-case preview.
   Follow the arrows on the diagram or hover over a line for its signed flow.
   L1 carries +51 MW and L5 carries −49 MW. All five lines are within their limits.
   Click **Run base case** to save the scenario.
2. Choose **L1** under **Line to remove** and click **Compare outage**. The
   diagram shows L1 as dashed. In **Line flows**, compare **Base (MW)** and
   **Outage (MW)** in the same row. L5 changes from −49 to −100 MW (133.33%
   of its 75 MW limit). L4 changes from −24 to −75 MW (125% of its 60 MW
   limit). The app saves both scenarios.
3. Open **Matrices & angles**. Select the scenario and matrix to show the full
   susceptance matrix, reduced matrix, or reduced inverse. The bus table shows
   the solved voltage angles, generation, and demand.
4. Open **Saved runs** and double-click a row to restore its inputs and results.
   Opening a saved outage also calculates the base case for comparison.

For an islanding demo, choose **Edit grid → Lines**, remove L1 and choose
**Apply model**. Then compare the outage of L2. The app identifies bus B as
disconnected from the reference and saves the unsolved contingency.

## Enter a grid (desktop)

Click **Edit lines** above the flow table to edit L1–L5 together, or double-click
a line's result row to jump to its reactance. You can change the line ID,
endpoints, reactance, and MW limit. **Apply model** recalculates the base case.
Click **Run base case** to save it or **Compare outage** to save both scenarios.

Choose **Edit grid**. In **Buses**, edit the bus IDs, generation, and demand
in MW. In **Lines**, choose each line's endpoints and enter a positive
reactance (per unit) and power limit (MW). Use **Add bus**, **Add line**, or
**Remove** to change the network. Choose a **Reference bus** and select
**Apply model** to preview the grid or **Cancel** to discard your edits.

The model supports 5–10 buses. IDs are case-sensitive. Parallel lines can share
endpoints if their IDs differ. The reference bus supplies the difference
between total demand and generation at the other buses. Its calculated
dispatch appears in **Matrices & angles**.

## Explain the calculation

For each active line, add 1/x to both endpoint diagonal entries of the
susceptance matrix B and subtract 1/x from both corresponding off-diagonal
entries. Every row sums to zero, so the all-ones vector is in the null space.
For a connected grid, fixing one angle at zero and removing that bus's row
and column makes the reduced matrix invertible.

The app computes the reduced inverse using Gauss–Jordan elimination with
partial pivoting. It multiplies the inverse by the non-reference net injections
(generation minus demand, divided by 100 MVA) to obtain the bus angles in radians.
The signed line flow is 100 × (from angle − to angle) / reactance in MW.
A negative value means the flow runs toward the listed from bus. Loading is
100 × |flow| / limit in percent. Active lines are sorted from highest to lowest
loading and flagged when flow exceeds the limit.

The graph uses adjacency lists to check connectivity after removing the selected
line. SQLite stores each run's inputs and outputs in `buses`, `lines`,
`demand_scenarios`, and `line_flows`.

## Divide the work among four teammates

| Teammate | Own and verify | Present |
| --- | --- | --- |
| 1 | Matrix construction, reference bus reduction, inversion, and angle solution. Check row sums and the reduced inverse. | Build B and explain the null space and reference bus. |
| 2 | Adjacency lists, single-line outages, signed flow, loading, and overload sorting. Verify the sample outage and islanding case. | Compare L1's outage with the base case and explain the changed flows. |
| 3 | SQLite schema, atomic saves, and reopening saved runs. Verify that inputs and results survive restart. | Open a saved run and explain the four tables. |
| 4 | Tkinter screens, input validation, sample data, and end-to-end demo. Verify the launch instructions and common input errors. | Enter the model and lead the live walkthrough. |

Each teammate can review one other teammate's module or responsibility before the demo.

