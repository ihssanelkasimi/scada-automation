import os
import snap7
from snap7 import Area
from snap7.util import get_bool, set_bool, get_dword, set_dword
from flask import Flask, jsonify, request
import json

# DLL
dll_path = r'C:\Users\HP\PycharmProjects\PythonProject\.venv\Scripts'
if os.path.exists(dll_path):
    os.add_dll_directory(dll_path)

# --- CONFIG ---
PLC_IP = '192.168.1.1'#pour automate reel 192.168...
RACK = 0
SLOT = 2

PE = Area.PE
PA = Area.PA

MK = Area.MK

# --- BITS DE MÉMOIRE (M) ---
BIT_MAP = {
    'march': (0, 0),
    'arret': (0, 1),
    'auto': (0, 3),
    'manu': (0, 4),
    'val': (0, 5),
    'reprise': (0, 6)
}

# --- ANALOGS (MD) ---
ANALOG_MAP = {
    'p1': 1, 'p2': 5, 'p3': 58
}

# --- LABELS DES SORTIES (A) ---
# Clé: (Byte, Bit)
# CORRECTION: Ajout des guillemets et des virgules
OUTPUT_LABELS = {
    (124, 0): "PM",
    (124, 1): "PTR",
    (124, 2): "EV1",
    (124, 3): "EV2",
    (124, 4): "EV3",
}

# --- LABELS DES ENTRÉES (E) ---
# Clé: (Byte, Bit)
# CORRECTION: Ajout des guillemets et des virgules
INPUT_LABELS = {
    (124, 1): "NH1",
    (124, 2): "NB1",
    (124, 3): "NB2",
    (124, 4): "NB3",
    (124, 5): "NH4",
    (124, 6): "NB4",
}

# --- ENTRÉES (E) / SORTIES (A) À LIRE (Basé sur les labels) ---
OUTPUT_BITS = list(OUTPUT_LABELS.keys())
INPUT_BITS = list(INPUT_LABELS.keys())

app = Flask(__name__)


# --- FONCTIONS PLC (Logique inchangée avec amélioration du diagnostic) ---
def connect():
    client = snap7.client.Client()
    try:
        client.connect(PLC_IP, RACK, SLOT)
        if client.get_connected(): return client
        print(f"Échec de la connexion au PLC à {PLC_IP}.")
        return None
    except Exception as e:
        print(f"ERREUR CRITIQUE DE CONNEXION: {e}")
        return None


def read_area(area, start, size):
    client = connect()
    if not client: return None
    try:
        data = client.read_area(area, 0, start, size)
        return data
    except Exception as e:
        print(f"Erreur de lecture de l'aire {area} à {start}: {e}")
        pass
    finally:
        if client: client.disconnect()
    return None


def write_bit(area, byte, bit, value):
    client = connect()
    if not client: return False
    try:
        data = client.read_area(area, 0, byte, 1)
        set_bool(data, 0, bit, value)
        client.write_area(area, 0, byte, data)
        print(f"WRITE BIT M{byte}.{bit} = {value} OK")
        return True
    except Exception as e:
        print(f"ERREUR WRITE BIT: {e}")
    finally:
        if client: client.disconnect()
    return False


def write_output_bit(area, byte, bit, value):
    client = connect()
    if not client: return False
    try:
        data = client.read_area(area, 0, byte, 1)
        set_bool(data, 0, bit, value)
        client.write_area(area, 0, byte, data)
        print(f"WRITE OUTPUT A{byte}.{bit} = {value} OK")
        return True
    except Exception as e:
        print(f"ERREUR WRITE OUTPUT BIT: {e}")
    finally:
        if client: client.disconnect()
    return False


def write_dword(start, value):
    client = connect()
    if not client: return False
    try:
        data = bytearray(4)
        set_dword(data, 0, value)
        client.write_area(MK, 0, start, data)
        print(f"WRITE DWORD MD{start} = {value} OK")
        return True
    except Exception as e:
        return False
    finally:
        if client: client.disconnect()
    return True


# --- ENDPOINTS FLASK ---

@app.route('/api/plc/status', methods=['GET'])
def status():
    """Endpoint de lecture de toutes les données PLC."""
    s = {}

    # Lecture A124.x (Sorties) et E124.x (Entrées)
    a124_data = read_area(PA, 124, 1)
    if a124_data is not None:
        for byte_addr, bit_addr in OUTPUT_BITS:
            key = f"Output_A{byte_addr}_{bit_addr}"
            s[key] = get_bool(a124_data, 0, bit_addr)

    e124_data = read_area(PE, 124, 1)
    if e124_data is not None:
        for byte_addr, bit_addr in INPUT_BITS:
            key = f"Input_E{byte_addr}_{bit_addr}"
            s[key] = get_bool(e124_data, 0, bit_addr)

    # Lecture M0.x (Mémoires)
    m0_data = read_area(MK, 0, 1)
    if m0_data is not None:
        for name, (byte, bit) in BIT_MAP.items():
            if byte == 0:
                s[f"Bit_{name}_M{byte}_{bit}"] = get_bool(m0_data, 0, bit)

    # Analogs DWORD
    for name, start in ANALOG_MAP.items():
        w_data = read_area(MK, start, 4)
        if w_data is not None:
            val = min(100, max(0, get_dword(w_data, 0)))
            s[f"Analog_{name}"] = val

    if not s:
        return jsonify({"status": "error",
                        "message": "Impossible de lire le PLC. Vérifiez la console Python pour l'erreur de connexion."}), 503

    return jsonify({"status": "success", "data": s, "message": None})


@app.route('/api/plc/command/bit/<bit_name>', methods=['POST'])
def write_bit_api(bit_name):
    if bit_name not in BIT_MAP:
        return jsonify({"status": "error", "message": "Bit Inconnu"}), 400
    if not request.json or 'state' not in request.json:
        return jsonify({"status": "error", "message": "JSON {'state': bool}"}), 400

    byte, bit = BIT_MAP[bit_name]
    ok = write_bit(MK, byte, bit, bool(request.json['state']))
    return jsonify({"status": "success" if ok else "error", "message": "OK" if ok else "Échec"})


@app.route('/api/plc/command/output/<output_label>', methods=['POST'])
def write_output_api(output_label):
    output_map = {v: k for k, v in OUTPUT_LABELS.items()}
    if output_label not in output_map:
        return jsonify({"status": "error", "message": "Output Inconnu"}), 400
    if not request.json or 'state' not in request.json:
        return jsonify({"status": "error", "message": "JSON {'state': bool}"}), 400

    byte, bit = output_map[output_label]
    ok = write_output_bit(PA, byte, bit, bool(request.json['state']))
    return jsonify({"status": "success" if ok else "error", "message": "OK" if ok else "Échec"})


@app.route('/api/plc/command/analog/<analog_name>', methods=['POST'])
def write_analog_api(analog_name):
    if analog_name not in ANALOG_MAP:
        return jsonify({"status": "error", "message": "Analog Inconnu"}), 400
    if not request.json or 'value' not in request.json:
        return jsonify({"status": "error", "message": "JSON {'value': int}"}), 400

    value = int(request.json['value'])
    if not 0 <= value <= 100:
        return jsonify({"status": "error", "message": "Valeur hors limites (0-100)"}), 400

    start = ANALOG_MAP[analog_name]
    ok = write_dword(start, value)
    return jsonify({"status": "success" if ok else "error", "message": "OK" if ok else "Échec"})


@app.route('/', methods=['GET'])
def index():
    js_bit_map = {}
    for name, (byte, bit) in BIT_MAP.items():
        js_bit_map[name] = [byte, bit]

    # Générer le HTML pour les Sorties (A124.x) avec boutons
    output_html = ""
    output_keys = []
    for byte_addr, bit_addr in OUTPUT_BITS:
        key = f"Output_A{byte_addr}_{bit_addr}"
        label = OUTPUT_LABELS[(byte_addr, bit_addr)]
        output_html += f'<p>{label} (A {byte_addr}.{bit_addr}): <span id="led-{key}" class="led led-off"></span> <span id="val-{key}">OFF</span> <button id="btn-output-{label}" class="off" onclick="toggleOutput(\'{label}\')" style="width: 50px; height:50px ">           </button></p>\n'
        output_keys.append(key)

    # Générer le HTML pour les Entrées (E124.x)
    input_html = ""
    input_keys = []
    for byte_addr, bit_addr in INPUT_BITS:
        key = f"Input_E{byte_addr}_{bit_addr}"
        label = INPUT_LABELS[(byte_addr, bit_addr)]
        input_html += f'<p>{label} (E {byte_addr}.{bit_addr}): <span id="led-{key}" class="led led-off"></span> <span id="val-{key}">OFF</span></p>\n'
        input_keys.append(key)

    # Correction des labels JS pour correspondre au format corrigé
    output_labels_js_corrected = {f"({k[0]}, {k[1]})": v for k, v in OUTPUT_LABELS.items()}
    input_labels_js_corrected = {f"({k[0]}, {k[1]})": v for k, v in INPUT_LABELS.items()}

    # La conversion des dictionnaires Python en chaînes JS doit être faite correctement
    import json

    output_labels_js_str = json.dumps(output_labels_js_corrected)
    input_labels_js_str = json.dumps(input_labels_js_corrected)

    # Note: Dans Flask, on utilise `json.dumps()` pour s'assurer que les chaînes sont valides en JS.
    # Dans l'exemple initial, le code JS n'utilisait pas ces labels, mais je les corrige au cas où.

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>PLC Test</title>
    <style>
        body {{font-family: Arial; background-color: #ffffff; color: #000000;}} 

        /* Flexbox pour aligner les blocs côte à côte */
        .flex-container {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap; 
        }}

        .section {{
            padding: 15px; 
            background: #f0f0f0; 
            margin-bottom: 15px; 
            border: 1px solid #000000; 
            border-radius: 0; 
            box-shadow: none;
            flex: 1; 
            min-width: 250px; 
        }} 

        button {{
            padding: 10px 15px; 
            margin: 5px; 
            border: 1px solid #000000; 
            border-radius: 0; 
            cursor: pointer; 
            background-color: #ffffff; 
            color: #000000; 
            transition: none;
        }} 

        /* COULEURS ET ÉTATS */
        .on {{background: #28a745; color: white; border-color: #000000;}} 
        .off {{background: #ffffff; color: #000000;}} 

        .led {{width: 15px; height: 15px; border-radius: 0; display: inline-block; margin: 5px; border: 1px solid #000000;}} 
        .led-on {{background: #28a745;}} 
        .led-off {{background: #ffffff;}} 

        input[type="number"] {{padding: 8px; border-radius: 0; border: 1px solid #000000; width: 60px;}}
    </style>
    </head>
    <body>
    <h1>Supervision Melange</h1>

    <div class="flex-container">
        <div class="section">
        <h2>ETAT Sorties (A 124.x)</h2>
        {output_html}
        </div>

        <div class="section">
        <h2>ETAT Entrées (E 124.x)</h2>
        {input_html}
        </div>
    </div>

    <div class="flex-container">
        <div class="section">
        <h2>Controle (M0.x)</h2>
        <p>Cliquez pour basculer l'état (ON/OFF).</p>
        <button id="btn-march" class="off" onclick="toggleBit('march')">March (M 0.0)</button>
        <button id="btn-arret" class="off" onclick="toggleBit('arret')">Arrêt (M 0.1)</button>
        <button id="btn-auto" class="off" onclick="toggleBit('auto')">Auto (M 0.3)</button>
        <button id="btn-manu" class="off" onclick="toggleBit('manu')">Manu (M 0.4)</button>
        <button id="btn-val" class="off" onclick="toggleBit('val')">Val (M 0.5)</button>
        <button id="btn-reprise" class="off" onclick="toggleBit('reprise')">Reprise (M 0.6)</button>
        </div>

        <div class="section">
        <h2>Recette:Pourcentage des Bacs</h2>
        <label>P1 (MD1): <input type="number" id="p1-input" min="0" max="100" value="0"> <button onclick="setAnalog('p1')">Valider</button></label><br>
        <label>P2 (MD5): <input type="number" id="p2-input" min="0" max="100" value="0"> <button onclick="setAnalog('p2')">Valider</button></label><br>
        <label>P3 (MD58): <input type="number" id="p3-input" min="0" max="100" value="0"> <button onclick="setAnalog('p3')">Valider</button></label>
        </div>
    </div>

    <div id="status" class="section">Status...</div>

    <script>
    let updateInterval;
    const BIT_MAP = {json.dumps(js_bit_map)};
    const ANALOG_MAP = {{'p1':1, 'p2':5, 'p3':58}};

    // Labels JavaScript (corrigés pour la syntaxe JS)
    const OUTPUT_LABELS_JS = {output_labels_js_str};
    const INPUT_LABELS_JS = {input_labels_js_str};

    // Clés utilisées pour la lecture dans result.data
    const OUTPUT_KEYS = ["Output_A124_0", "Output_A124_1", "Output_A124_2", "Output_A124_3", "Output_A124_4"];
    const INPUT_KEYS = ["Input_E124_1", "Input_E124_2", "Input_E124_3", "Input_E124_4", "Input_E124_5", "Input_E124_6"];

    const OUTPUT_LABEL_MAP = {{"Output_A124_0": "PM", "Output_A124_1": "PTR", "Output_A124_2": "EV1", "Output_A124_3": "EV2", "Output_A124_4": "EV3"}};

    const bitStates = {{}}; 
    const outputStates = {{}}; 
    const writtenAnalogValues = {{}}; 

    // --- Fonctions de Commande (Inchangées) ---
    async function toggleBit(name) {{
        const currentState = bitStates[name] || false; 
        const newState = !currentState;

        const btn = document.getElementById('btn-' + name);
        btn.style.opacity = '0.5'; 
        await setBit(name, newState);
        setTimeout(() => {{btn.style.opacity = '1';}}, 100); 
    }}

    async function toggleOutput(label) {{
        const stateKey = `output-${{label}}`;
        const currentState = outputStates[stateKey] || false; 
        const newState = !currentState;

        const btn = document.getElementById('btn-output-' + label);
        btn.style.opacity = '0.5'; 
        await setOutput(label, newState);
        setTimeout(() => {{btn.style.opacity = '1';}}, 100); 
    }}

    async function setBit(name, state) {{
        const resp = await fetch(`/api/plc/command/bit/${{name}}`, {{
            method:'POST', 
            headers:{{'Content-Type':'application/json'}}, 
            body:JSON.stringify({{state}})
        }});
        const result = await resp.json();
        if (result.status !== 'success') console.error('Bit erreur: ' + result.message);
        updateStatus(); 
    }}

    async function setOutput(label, state) {{
        const resp = await fetch(`/api/plc/command/output/${{label}}`, {{
            method:'POST', 
            headers:{{'Content-Type':'application/json'}}, 
            body:JSON.stringify({{state}})
        }});
        const result = await resp.json();
        if (result.status !== 'success') console.error('Output erreur: ' + result.message);
        updateStatus(); 
    }}

    async function setAnalog(name) {{
        const input = document.getElementById(name + '-input');
        const val = parseInt(input.value) || 0;

        if (val < 0 || val > 100) {{ alert('Valeur doit être entre 0 et 100.'); return; }}

        writtenAnalogValues[name] = val; 

        const resp = await fetch(`/api/plc/command/analog/${{name}}`, {{
            method:'POST', 
            headers:{{'Content-Type':'application/json'}}, 
            body:JSON.stringify({{value:val}})
        }});
        const result = await resp.json();

        if (result.status === 'success') {{
            input.value = val; 

            clearInterval(updateInterval);
            document.getElementById('status').textContent = `Écriture ${{name}} OK. Reprise rafraîchissement dans 1s...`;

            setTimeout(() => {{
                delete writtenAnalogValues[name]; 
                updateStatus(); 
                updateInterval = setInterval(updateStatus, 2000); 
            }}, 1000); 

        }} else {{
            alert('Erreur write: ' + result.message + ' - Vérif console Python');
            input.style.border = '2px solid red';
            delete writtenAnalogValues[name]; 
        }}
    }}

    // --- Fonction de Supervision (Mise à jour des Entrées/Sorties) ---
    async function updateStatus() {{
        const resp = await fetch('/api/plc/status');
        const result = await resp.json();
        const statusElement = document.getElementById('status');

        if (result.status === 'success') {{
            const d = result.data;

            // Mise à jour des Sorties (A 124.x)
            OUTPUT_KEYS.forEach(key => {{
                const state = d[key] || false;
                document.getElementById('led-' + key).className = 'led ' + (state ? 'led-on' : 'led-off');
                document.getElementById('val-' + key).textContent = state ? 'ON' : 'OFF';

                const label = OUTPUT_LABEL_MAP[key];
                if (label) {{
                    const stateKey = `output-${{label}}`;
                    outputStates[stateKey] = state;
                    const btn = document.getElementById('btn-output-' + label);
                    if (btn) {{
                        btn.className = state ? 'on' : 'off';
                    }}
                }}
            }});

            // Mise à jour des Entrées (E 124.x)
            INPUT_KEYS.forEach(key => {{
                const state = d[key] || false;
                document.getElementById('led-' + key).className = 'led ' + (state ? 'led-on' : 'led-off');
                document.getElementById('val-' + key).textContent = state ? 'ON' : 'OFF';
            }});

            // Bits Bistables (M0.x)
            Object.keys(BIT_MAP).forEach(name => {{
                const [byte, bit] = BIT_MAP[name];
                const state = d[`Bit_${{name}}_M${{byte}}_${{bit}}`] || false;

                bitStates[name] = state; 

                const btn = document.getElementById('btn-' + name);

                btn.className = state ? 'on' : 'off'; 
                btn.textContent = name.charAt(0).toUpperCase() + name.slice(1) + ` (M ${{byte}}.${{bit}})`;
            }});

            // Analogs (Fix du Revert)
            Object.keys(ANALOG_MAP).forEach(name => {{
                const val = d[`Analog_${{name}}`] || 0;
                const input = document.getElementById(name + '-input');

                if (writtenAnalogValues.hasOwnProperty(name)) {{
                    // Laisser la valeur entrée par l'utilisateur
                }}
                else if (document.activeElement !== input) {{
                    input.value = val;
                }}
            }});

            statusElement.textContent = 'Connexion OK - Update: ' + new Date().toLocaleTimeString();

        }} else {{
            statusElement.textContent = 'Erreur: ' + result.message;
        }}
    }}

    updateInterval = setInterval(updateStatus, 2000);
    updateStatus();
    </script>
    </body>
    </html>
    """
    return html


if __name__ == '__main__':
    # Clean P1/P2/P3 à 0 au démarrage
    for name, start in ANALOG_MAP.items():
        write_dword(start, 0)

    print("Flask démarré. Vérifiez votre navigateur.")
    app.run(debug=True, host='0.0.0.0', port=5000)