import sys
from pathlib import Path  # if you haven't already done so
import json


from conversion_lib import qiskit_circuit_to_ore

# Import the qv function.
import qiskit.ignis.verification.quantum_volume as qv


basis_selector = 1
basis_gates_array = [
    [],
    ["rx", "ry", "rz", "cx"],  # a common basis set, default
    ["cx", "rz", "sx", "x"],  # IBM default basis set
    ["rx", "ry", "rxx"],  # IonQ default basis set
    ["h", "p", "cx"],  # another common basis set
    ["u", "cx"],  # general unitaries basis gates
]


def test():
    min_qubits = 2
    max_qubits = 5
    max_circuits = 1
    qubit_lists = [list(range(i)) for i in range(min_qubits, max_qubits + 1)]
    _qv_circs, qv_circs_nomeas = qv.qv_circuits(qubit_lists, max_circuits)
    for circuit_group in qv_circs_nomeas:
        for circuit in circuit_group:
            ionq_circuit, converted = qiskit_circuit_to_ore.convert(
                circuit, basis_gates=basis_gates_array[basis_selector]
            )
            circuit_name = ionq_circuit["name"]
            circuit_path = Path(f"./{circuit_name}.json")
            circuit_path.write_text(json.dumps(ionq_circuit["input"]))
            converted_path = Path(f"./{circuit_name}.qore.python_baseline")
            converted_path.write_text(converted)


test()
