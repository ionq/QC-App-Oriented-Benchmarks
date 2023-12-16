import sys
from pathlib import Path  # if you haven't already done so

file = Path(__file__).resolve()
parent, root = file.parent, file.parents[1]
sys.path.append(str(root))

import qiskit_circuit_to_ore

# Import the qv function.
import qiskit.ignis.verification.quantum_volume as qv
from qiskit import execute, Aer, transpile


basis_selector = 1
basis_gates_array = [
    [],
    ['rx', 'ry', 'rz', 'cx'],       # a common basis set, default
    ['cx', 'rz', 'sx', 'x'],        # IBM default basis set
    ['rx', 'ry', 'rxx'],            # IonQ default basis set
    ['h', 'p', 'cx'],               # another common basis set
    ['u', 'cx']                     # general unitaries basis gates
]


def test():
    min_qubits = 2
    max_qubits = 5
    max_circuits = 1
    qubit_lists = [list(range(i)) for i in range(min_qubits, max_qubits + 1)]
    qv_circs, qv_circs_nomeas = qv.qv_circuits(qubit_lists, max_circuits)
    for circuit_group in qv_circs_nomeas:
        for circuit in circuit_group:
            qiskit_circuit_to_ore.convert(circuit, basis_gates=basis_gates_array[basis_selector])


test()
