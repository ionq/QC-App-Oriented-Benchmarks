from qiskit2qore import qiskit_circuit_to_ore
from chiron.dump import ore
from chiron.load.qore import load_qore
from chiron.dump import ore

import json
import subprocess
from pathlib import Path

basis_selector = 1
basis_gates_array = [
    [],
    ["rx", "ry", "rz", "cx"],  # a common basis set, default
    ["cx", "rz", "sx", "x"],  # IBM default basis set
    ["rx", "ry", "rxx"],  # IonQ default basis set
    ["h", "p", "cx"],  # another common basis set
    ["u", "cx"],  # general unitaries basis gates
]


def run_preprocessor(qore_path: Path) -> Path:
    """
    runs the python preprocessor on the saved qore file, and returns the filename
    of the preprocessed qore
    """
    command = ["python", "preprocessor2.py", str(qore_path)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return_code = process.wait()
    if return_code != 0:
        raise TypeError(f"Subprocess failed with return code: {return_code}")
    return Path(f"{str(qore_path)}_preprocessed")


def dump_qiskit_circuit_assets(qiskit_circuit, preprocessor=False):
    ionq_circuit, converted_qore = qiskit_circuit_to_ore.convert(
        qiskit_circuit, basis_gates=basis_gates_array[basis_selector]
    )
    circuit_name = ionq_circuit["name"]
    circuit_path = Path(f"./{circuit_name}.json")
    circuit_path.write_text(json.dumps(ionq_circuit["input"]))
    converted_path = Path(f"./{circuit_name}.qore")
    converted_path.write_text(converted_qore)
    chiron_circuit = load_qore(converted_qore)
    ore_circuit = ore.dumps(chiron_circuit, indent=4)
    orefile_path = Path(f"./{circuit_name}.ore")
    orefile_path.write_text(ore_circuit)
    if preprocessor:
        converted_path = run_preprocessor(converted_path)
        converted_qore = converted_path.read_text()
        chiron_circuit = load_qore(converted_qore)
        ore_circuit = ore.dumps(chiron_circuit, indent=4)
        converted_path = Path(f"./{circuit_name}_preprocessed.ore")
        converted_path.write_text(ore_circuit)
