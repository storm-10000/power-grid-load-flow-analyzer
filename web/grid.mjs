export const BASE_MVA = 100;
export const SAMPLE = {
  buses: `A, 100, 0
B, 0, 30
C, 0, 20
D, 0, 25
E, 0, 25`,
  lines: `L1, A, B, 0.10, 75
L2, B, C, 0.10, 60
L3, C, D, 0.10, 60
L4, D, E, 0.10, 60
L5, E, A, 0.10, 75`,
  reference: 'A',
};

function rows(source, size, label) {
  return source.split(/\r?\n/).flatMap((row, index) => {
    if (!row.trim()) return [];
    const fields = row.split(',').map((field) => field.trim());
    if (fields.length !== size || fields.some((field) => !field)) {
      throw new Error(`${label} row ${index + 1} needs ${size} comma-separated values.`);
    }
    return [fields];
  });
}

function quantity(value, label, positive = false) {
  const result = Number(value);
  const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
  if (!decimal.test(value) || !Number.isFinite(result) || result < 0 || (positive && result === 0)) {
    throw new Error(`${label} must be finite and ${positive ? 'positive' : 'nonnegative'}.`);
  }
  return result;
}

export function parseModel(busText, lineText, reference) {
  const buses = new Map();
  const lines = new Map();
  for (const [id, generation, demand] of rows(busText, 3, 'Bus')) {
    if (buses.has(id)) throw new Error(`Duplicate bus ID ${id}.`);
    buses.set(id, { generation: quantity(generation, `${id} generation`), demand: quantity(demand, `${id} demand`) });
  }
  if (buses.size < 5 || buses.size > 10) throw new Error('Enter 5 to 10 buses.');
  if (!buses.has(reference)) throw new Error('The reference bus must be an existing bus ID.');
  for (const [id, start, end, reactance, limit] of rows(lineText, 5, 'Line')) {
    if (lines.has(id)) throw new Error(`Duplicate line ID ${id}.`);
    if (!buses.has(start) || !buses.has(end) || start === end) {
      throw new Error(`Line ${id} needs two distinct, existing buses.`);
    }
    lines.set(id, { id, start, end, reactance: quantity(reactance, `${id} reactance`, true), limit: quantity(limit, `${id} limit`, true) });
  }
  return { buses, lines, reference };
}

function invert(matrix) {
  const size = matrix.length;
  const scale = Math.max(...matrix.flat().map(Math.abs));
  const augmented = matrix.map((row, index) => [...row, ...matrix.map((_, column) => Number(index === column))]);
  for (let column = 0; column < size; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < size; row += 1) {
      if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) pivot = row;
    }
    if (Math.abs(augmented[pivot][column]) <= 1e-12 * scale) {
      throw new Error('The reduced matrix is numerically singular. Check the reactances.');
    }
    [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
    const divisor = augmented[column][column];
    const pivotRow = augmented[column].map((value) => value / divisor);
    augmented[column] = pivotRow;
    for (let row = 0; row < size; row += 1) {
      if (row !== column) {
        const factor = augmented[row][column];
        augmented[row] = augmented[row].map((value, index) => value - factor * pivotRow[index]);
      }
    }
  }
  return augmented.map((row) => row.slice(size));
}

export function solve({ buses, lines, reference }, outage = null) {
  if (outage !== null && !lines.has(outage)) throw new Error('Choose an existing line ID for the outage.');
  const ids = [...buses.keys()];
  const indices = new Map(ids.map((id, index) => [id, index]));
  const adjacency = new Map(ids.map((id) => [id, []]));
  const matrix = ids.map(() => ids.map(() => 0));
  for (const { id, start, end, reactance } of lines.values()) {
    if (id === outage) continue;
    adjacency.get(start).push(end);
    adjacency.get(end).push(start);
    const from = indices.get(start);
    const to = indices.get(end);
    const weight = 1 / reactance;
    matrix[from][from] += weight;
    matrix[to][to] += weight;
    matrix[from][to] -= weight;
    matrix[to][from] -= weight;
  }

  const visited = new Set([reference]);
  const pending = [reference];
  while (pending.length) {
    for (const neighbor of adjacency.get(pending.pop())) {
      if (visited.has(neighbor)) continue;
      visited.add(neighbor);
      pending.push(neighbor);
    }
  }
  const unreachable = ids.filter((id) => !visited.has(id));
  if (unreachable.length) {
    throw new Error(`Grid is disconnected. Buses outside the reference island: ${unreachable.join(', ')}.`);
  }

  const reducedIds = ids.filter((id) => id !== reference);
  const reducedIndices = reducedIds.map((id) => indices.get(id));
  const reduced = reducedIndices.map((row) => reducedIndices.map((column) => matrix[row][column]));
  if (!matrix.flat().every(Number.isFinite)) throw new Error('Reactances exceed the supported numeric range.');
  const inverse = invert(reduced);
  const net = reducedIds.map((id) => {
    const { generation, demand } = buses.get(id);
    return (generation - demand) / BASE_MVA;
  });
  const angles = new Map([[reference, 0]]);
  reducedIds.forEach((id, index) => {
    angles.set(id, inverse[index].reduce((total, value, column) => total + value * net[column], 0));
  });
  const dispatch = buses.get(reference).demand - BASE_MVA * net.reduce((total, value) => total + value, 0);
  if (![...inverse.flat(), ...angles.values(), dispatch].every(Number.isFinite)) {
    throw new Error('The model exceeds the supported numeric range.');
  }
  if (dispatch < -1e-8) throw new Error('The reference bus would need negative generation. Adjust generation or demand.');

  const flows = [...lines.values()].map((line) => {
    const { id, start, end, reactance, limit } = line;
    const mw = id === outage ? 0 : (angles.get(start) - angles.get(end)) * BASE_MVA / reactance;
    const loading = Math.abs(mw) / limit * 100;
    if (!Number.isFinite(loading)) throw new Error('Line loading exceeds the supported numeric range.');
    return { ...line, mw, loading, state: id === outage ? 'OUT' : loading > 100 + 1e-8 ? 'OVERLOAD' : 'OK' };
  });
  flows.sort((first, second) => Number(first.state === 'OUT') - Number(second.state === 'OUT')
    || second.loading - first.loading || (first.id < second.id ? -1 : Number(first.id > second.id)));
  return { ids, reducedIds, matrix, reduced, inverse, angles, slackGeneration: Math.max(0, dispatch), flows };
}
