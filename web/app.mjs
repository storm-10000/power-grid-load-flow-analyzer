import { SAMPLE, parseModel, solve } from './grid.mjs';

const get = (id) => document.getElementById(id);
const outageInput = get('outage');
const matrixType = get('matrix-type');
const diagram = get('diagram');
const status = get('status');
const modelError = get('model-error');
const svgNamespace = 'http://www.w3.org/2000/svg';
let model;
let base;
let current;
let outage;

const number = (value, digits = 2) => value === undefined ? '—' : value.toFixed(digits);
const flow = (value) => value > 0 && value >= 0.005 ? `+${number(value)}` : number(value);
const flowsById = (result) => new Map((result?.flows ?? []).map((line) => [line.id, line]));

function svg(tag, attributes, text) {
  const node = document.createElementNS(svgNamespace, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderDiagram() {
  const ids = [...model.buses.keys()];
  const positions = new Map(ids.map((id, index) => {
    const angle = 2 * Math.PI * index / ids.length - Math.PI / 2;
    return [id, { x: 270 + 196 * Math.cos(angle), y: 155 + 101 * Math.sin(angle), angle }];
  }));
  const results = flowsById(current);
  const groups = new Map();
  for (const line of model.lines.values()) {
    const key = JSON.stringify([line.start, line.end].sort());
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(line);
  }
  diagram.replaceChildren();
  diagram.setAttribute('aria-label', `Grid topology for ${outage === null ? 'the base case' : `the ${outage} outage`}. Line details are in the Line flows table.`);

  for (const group of groups.values()) {
    group.forEach(({ id, start, end }, index) => {
      const from = positions.get(start);
      const to = positions.get(end);
      const deltaX = to.x - from.x;
      const deltaY = to.y - from.y;
      const length = Math.hypot(deltaX, deltaY);
      const alongX = deltaX / length;
      const alongY = deltaY / length;
      const offset = (index - (group.length - 1) / 2) * 16 * (start < end ? 1 : -1);
      const bendX = (from.x + to.x) / 2 - alongY * offset * 2;
      const bendY = (from.y + to.y) / 2 + alongX * offset * 2;
      const result = results.get(id);
      const style = id === outage ? 'out' : result?.state === 'OVERLOAD' ? 'overload' : 'normal';
      const branch = svg('g', { class: style });
      branch.append(svg('title', {}, `${id}: ${id === outage ? 'out of service' : result ? `${flow(result.mw)} MW from ${start} to ${end}` : 'flow unavailable'}`));
      branch.append(svg('path', { d: `M ${from.x} ${from.y} Q ${bendX} ${bendY} ${to.x} ${to.y}`, fill: 'none', class: `svg-line ${style}` }));
      const midX = (from.x + 2 * bendX + to.x) / 4;
      const midY = (from.y + 2 * bendY + to.y) / 4;
      if (result && Math.abs(result.mw) > 1e-8) {
        const direction = Math.sign(result.mw);
        const rotate = Math.atan2(deltaY, deltaX) * 180 / Math.PI + (direction < 0 ? 180 : 0);
        branch.append(svg('path', { d: 'M -6 -5 L 7 0 L -6 5 Z', transform: `translate(${midX} ${midY}) rotate(${rotate})`, class: 'svg-arrow' }));
      }
      const side = start < end ? 1 : -1;
      branch.append(svg('text', { x: midX - alongY * 10 * side, y: midY + alongX * 10 * side + 4, class: 'svg-line-id' }, id));
      diagram.append(branch);
    });
  }

  for (const [id, { x, y, angle }] of positions) {
    const reference = id === model.reference;
    diagram.append(svg('circle', { cx: x, cy: y, r: 12, class: reference ? 'svg-bus reference' : 'svg-bus' }));
    if (reference) diagram.append(svg('text', { x, y, class: 'svg-reference' }, 'R'));
    diagram.append(svg('text', { x: x + 25 * Math.cos(angle), y: y + 25 * Math.sin(angle) + 4, class: 'svg-bus-id' }, id));
  }
}

function cell(row, value, heading = null) {
  const node = document.createElement(heading ? 'th' : 'td');
  if (heading) node.scope = heading;
  node.textContent = value;
  row.append(node);
  return node;
}

function renderFlows() {
  const table = get('flows');
  table.replaceChildren();
  const baseFlows = flowsById(base);
  const shownFlows = flowsById(current);
  const lines = current?.flows ?? base?.flows ?? [...model.lines.values()];
  if (!lines.length) {
    const empty = cell(table.insertRow(), 'No transmission lines in this model.');
    empty.colSpan = 7;
  }
  for (const { id, start, end, limit } of lines) {
    const row = table.insertRow();
    const result = shownFlows.get(id);
    const state = id === outage ? 'OUT' : result?.state;
    row.className = state === 'OVERLOAD' ? 'flow-overload' : state === 'OUT' ? 'flow-out' : '';
    cell(row, id, 'row');
    cell(row, `${start} → ${end}`);
    cell(row, number(limit));
    cell(row, flow(baseFlows.get(id)?.mw));
    cell(row, outage === null ? '—' : flow(id === outage ? 0 : result?.mw));
    cell(row, state === 'OUT' ? '0.00%' : result ? `${number(result.loading)}%` : '—');
    cell(row, { OK: 'Within limit', OVERLOAD: 'Overloaded', OUT: 'Out of service' }[state] ?? 'Unsolved');
  }
}

function renderMatrix() {
  const angles = get('angles');
  const table = get('matrix');
  angles.replaceChildren();
  table.replaceChildren();
  matrixType.disabled = !current;
  get('matrix-status').textContent = current
    ? `Showing ${outage === null ? 'the base case' : `the ${outage} outage`}. The reference bus angle is fixed at zero.`
    : 'No angles or matrices are available for the unsolved scenario.';
  if (!current) return;
  for (const [id, { generation, demand }] of model.buses) {
    const row = angles.insertRow();
    const reference = id === model.reference;
    cell(row, reference ? `${id} (reference)` : id, 'row');
    cell(row, number(current.angles.get(id), 6));
    cell(row, number(reference ? current.slackGeneration : generation));
    cell(row, number(demand));
  }
  const key = matrixType.value;
  const ids = key === 'matrix' ? current.ids : current.reducedIds;
  const headers = table.createTHead().insertRow();
  cell(headers, 'Bus', 'col');
  ids.forEach((id) => cell(headers, id, 'col'));
  const body = table.createTBody();
  current[key].forEach((values, index) => {
    const row = body.insertRow();
    cell(row, ids[index], 'row');
    values.forEach((value) => cell(row, number(value, 5)));
  });
}

function renderScenario(selectedOutage) {
  outage = selectedOutage;
  current = null;
  try {
    current = solve(model, outage);
    status.textContent = outage === null ? 'Base case solved.' : `${outage} removed. Outage case solved.`;
    status.classList.remove('problem');
  } catch (error) {
    status.textContent = error.message;
    status.classList.add('problem');
  }
  if (outage === null) base = current;
  get('case-label').textContent = outage === null ? 'Base case' : `${outage} outage`;
  const demand = [...model.buses.values()].reduce((total, bus) => total + bus.demand, 0);
  get('demand').textContent = Number.isFinite(demand) ? `${number(demand)} MW` : 'Out of range';
  get('peak').textContent = current ? `${number(current.flows[0]?.loading ?? 0)}%` : '—';
  get('overloaded').textContent = current?.flows.filter((line) => line.state === 'OVERLOAD').length ?? '—';
  renderDiagram();
  renderFlows();
  renderMatrix();
}

function applyModel() {
  try {
    model = parseModel(get('buses').value, get('lines').value, get('reference').value.trim());
  } catch (error) {
    modelError.textContent = error.message;
    modelError.hidden = false;
    return;
  }
  modelError.hidden = true;
  outageInput.replaceChildren();
  for (const { id, start, end } of model.lines.values()) {
    outageInput.add(new Option(`${id} · ${start} → ${end}`, id));
  }
  if (!model.lines.size) outageInput.add(new Option('No lines available', ''));
  outageInput.disabled = get('compare').disabled = !model.lines.size;
  renderScenario(null);
  if (!current) {
    modelError.textContent = `Model applied, but it could not be solved. ${status.textContent}`;
    modelError.hidden = false;
  }
}

function loadSample() {
  for (const [name, value] of Object.entries(SAMPLE)) get(name).value = value;
  applyModel();
}

get('scenario-form').addEventListener('submit', (event) => {
  event.preventDefault();
  if (!outageInput.disabled) renderScenario(outageInput.value);
});
get('base').addEventListener('click', () => renderScenario(null));
get('model-form').addEventListener('submit', (event) => {
  event.preventDefault();
  applyModel();
});
get('sample').addEventListener('click', loadSample);
matrixType.addEventListener('change', renderMatrix);
loadSample();
