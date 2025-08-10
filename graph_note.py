from flask import Flask, render_template_string, request, jsonify
import json, os
import webbrowser
app = Flask(__name__)
DATA_FILE = 'graph.json'

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Knowledge Graph Notes</title>
  <style>
    body, html { margin:0; padding:0; height:100%; overflow:hidden; }
    #controls { position:absolute; top:10px; left:10px; z-index:20; background:white; padding:5px; border-radius:8px; }
    #controls input, #controls button { margin:3px; padding:5px; }
    #cy { width:100%; height:100%; display:block; }
    #styleModal, #addNodeModal {
      position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
      background:white; padding:20px; border:1px solid #ccc; display:none;
      z-index:100; border-radius:8px;
    }
    .color-btn, .shape-btn { width:30px; height:30px; margin:2px; border:none; cursor:pointer; }
    .color-btn:hover, .shape-btn:hover { outline:2px solid black; }
    #overlay {
      position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.3);
      display:none; z-index:99;
    }
  </style>
  <script src="/static/cytoscape.min.js"></script>
</head>
<body>
<div id="overlay"></div>
<div id="controls">
  <input id="search" placeholder="Search nodes...">
  <button id="fitButton">Fit All</button>
  <button id="layoutButton">Refresh Layout</button>
  <button id="styleButton">Style</button>
  <button id="deleteButton">Delete</button>
  <button id="addButton">Add</button>
</div>
<div id="cy"></div>

<!-- Style Modal -->
<div id="styleModal">
  <div>Choose color:</div>
  <div id="colorChoices"></div>
  <div>Choose shape:</div>
  <div id="shapeChoices"></div>
  <button onclick="applyStyle()">Apply</button>
  <button onclick="hideModal()">Cancel</button>
</div>

<!-- Add Node Modal -->
<div id="addNodeModal">
  <div><input placeholder="New node label" id="newNodeLabel"></div>
  <div id="connections"></div>
  <button onclick="addConnectionInput()">+ Add connection</button>
  <br><br>
  <button onclick="submitAddNode()">Add Node</button>
  <button onclick="hideModal()">Cancel</button>
</div>

<script>
let cy;
let lastNode = null;
let selectedNodes = [];

function saveGraph() {
  fetch('/save', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ nodes: cy.nodes().jsons(), edges: cy.edges().jsons() })
  });
}

function saveAndRelayout() {
  saveGraph();
  runLayout();
}

function runLayout() {
  cy.layout({ name: 'cose', animate: true, randomize: false, fit: false }).run();
  updateNodeSizes();
}

function updateNodeSizes() {
  cy.nodes().forEach(n => {
    let size = 40 + n.degree() * 5;
    n.style({ width: size, height: size });
  });
}

function initGraph(data) {
  cy = cytoscape({
    container: document.getElementById('cy'),
    elements: data.nodes.concat(data.edges),
    style: [
      { selector: 'node', style: {
          'label': 'data(label)', 'text-valign': 'center', 'color': '#333', 'background-color': '#ddd', 'shape': 'ellipse', 'border-width': 2, 'border-color': '#ccc' }
      },
      { selector: 'edge', style: { 'width': 3, 'line-color': '#aaa', 'curve-style': 'bezier' } },
      { selector: '.highlight', style: { 'border-color': '#0099ff', 'border-width': 6 } },
      { selector: '.neighbor', style: { 'border-color': '#a0d8ff', 'border-width': 4 } },
      { selector: 'edge.neighbor', style: { 'line-color': '#a0d8ff', 'width': 4 } },
      { selector: '.dimmed', style: { 'opacity': 0.2 } }
    ],
    layout: { name: 'cose', animate: true },
    wheelSensitivity: 10
  });

  cy.userZoomingEnabled(true);
  cy.userPanningEnabled(true);

  cy.on('mousedown', function(evt) {
    if (evt.originalEvent.button === 1) {
      cy.userPanningEnabled(true);
    }
  });
  cy.on('mouseup', function(evt) {
    if (evt.originalEvent.button === 1) {
      cy.userPanningEnabled(false);
    }
  });

  cy.on('boxselect', () => {
    selectedNodes = cy.nodes(':selected').toArray();
  });

  cy.on('select unselect', 'node', () => {
    cy.nodes().removeClass('highlight neighbor');
    cy.edges().removeClass('highlight neighbor');

    selectedNodes = cy.nodes(':selected').toArray();

    if (selectedNodes.length === 0) return;

    selectedNodes.forEach(n => {
      n.addClass('highlight');
      n.connectedEdges().forEach(e => {
        let other = e.source().id() === n.id() ? e.target() : e.source();
        if (!other.selected()) other.addClass('neighbor');
        e.addClass('neighbor');
      });
    });
  });

  cy.on('dblclick', evt => {
    if (evt.target === cy) {
      let id = 'n' + Date.now();
      cy.add({ group: 'nodes', data: { id: id, label: 'New Note' }, position: evt.position });
      saveGraph();
    }
  });

  cy.on('dblclick', 'node', evt => {
    let node = evt.target;
    let txt = prompt('Edit text:', node.data('label'));
    if (txt !== null) {
      node.data('label', txt);
      saveGraph(); // 不重排
    }
  });

  cy.on('cxttap', 'node', evt => {
    if (!lastNode) {
      lastNode = evt.target;
    } else if (lastNode.id() === evt.target.id()) {
      lastNode = null;
    } else {
      cy.add({
        group: 'edges',
        data: {
          id: lastNode.id() + '-' + evt.target.id(),
          source: lastNode.id(),
          target: evt.target.id()
        }
      });
      lastNode = null;
      saveGraph(); // 不重排
    }
  });

  // 修改：删除连接时不再触发 runLayout()
  cy.on('cxttap', 'edge', evt => {
    if (confirm('Delete connection?')) {
      cy.remove(evt.target);
      saveGraph(); // 不重排
    }
  });

  cy.on('dragfree', 'node', () => saveGraph());

  document.getElementById('search').addEventListener('input', function() {
    let term = this.value.toLowerCase();
    cy.nodes().forEach(n => n.toggleClass('dimmed', term && !n.data('label').toLowerCase().includes(term)));
  });

  document.getElementById('fitButton').addEventListener('click', () => { cy.fit(); });
  document.getElementById('layoutButton').addEventListener('click', runLayout);
  document.getElementById('styleButton').addEventListener('click', () => showStyleModal());
  document.getElementById('deleteButton').addEventListener('click', () => {
    if (confirm('Delete selected nodes?')) {
      cy.nodes(':selected').remove(); saveAndRelayout();
    }
  });
  document.getElementById('addButton').addEventListener('click', () => showAddModal());

  updateNodeSizes();
}

const colors = ['#f00','#0f0','#00f','#ff0','#0ff','#f0f','#999','#333','#666','#ccc','#aaf','#faa','#afa','#ffa','#cfc','#fcc','#ccf','#aaa','#ddd','#bbb'];
const shapes = ['ellipse','triangle','rectangle','diamond','hexagon'];

function showStyleModal() {
  document.getElementById('overlay').style.display = 'block';
  document.getElementById('styleModal').style.display = 'block';
  document.getElementById('colorChoices').innerHTML = colors.map(c => `<button class='color-btn' style='background:${c}' onclick='selectColor("${c}")'></button>`).join('');
  document.getElementById('shapeChoices').innerHTML = shapes.map(s => `<button class='shape-btn' onclick='selectShape("${s}")'>${s}</button>`).join('');
  selectedStyle = { color:null, shape:null };
}

function showAddModal() {
  document.getElementById('overlay').style.display = 'block';
  document.getElementById('addNodeModal').style.display = 'block';
  document.getElementById('connections').innerHTML = '<input class="conn" placeholder="Connect to label">';
}

function hideModal() {
  document.getElementById('overlay').style.display = 'none';
  document.querySelectorAll('#styleModal,#addNodeModal').forEach(el => el.style.display='none');
}

function addConnectionInput() {
  let input = document.createElement('input');
  input.className = 'conn';
  input.placeholder = 'Connect to label';
  document.getElementById('connections').appendChild(input);
}

let selectedStyle = { color:null, shape:null };

function selectColor(c) { selectedStyle.color = c; }
function selectShape(s) { selectedStyle.shape = s; }

function applyStyle() {
  (cy.nodes(':selected')).forEach(n => {
    if (selectedStyle.color) n.style('background-color', selectedStyle.color);
    if (selectedStyle.shape) n.style('shape', selectedStyle.shape);
  });
  hideModal(); saveGraph();
}

function submitAddNode() {
  let label = document.getElementById('newNodeLabel').value;
  if (!label) return;
  let id = 'n' + Date.now();
  cy.add({ group:'nodes', data:{ id: id, label: label }, position: { x:100, y:100 } });
  let inputs = document.querySelectorAll('.conn');
  inputs.forEach(inp => {
    let targetLabel = inp.value.trim();
    if (!targetLabel) return;
    let target = cy.nodes().filter(n => n.data('label') === targetLabel);
    if (target.length > 0) {
      cy.add({ group:'edges', data:{ id:id+'-'+target[0].id(), source:id, target:target[0].id() }});
    }
  });
  hideModal(); saveGraph();
}

fetch('/load').then(r => r.json()).then(initGraph);
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(TEMPLATE)

@app.route('/load')
def load_graph():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {"nodes": [], "edges": []}
    return jsonify(data)

@app.route('/save', methods=['POST'])
def save_graph():
    data = request.get_json()
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    return jsonify({"status": "ok"})



if __name__ == '__main__':
    webbrowser.open('http://127.0.0.1:5000')  # 自动打开浏览器

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)