from qiskit_ionq.helpers import qiskit_to_ionq
from qiskit import transpile
from conversion_lib.circuit import Circuit


class LocalOrefileBackend:
    def gateset(self):
        return "qis"

    def name(self):
        return "local_orefile"


def convert_to_ionq_circuit(qiskit_circuit, basis_gates):
    basis_circuit = transpile(
        qiskit_circuit, basis_gates=basis_gates, seed_transpiler=0
    )
    ionq_circuit = qiskit_to_ionq(basis_circuit, LocalOrefileBackend())
    return ionq_circuit


def convert(qiskit_circuit, basis_gates):
    ionq_circuit = convert_to_ionq_circuit(qiskit_circuit, basis_gates)
    circuit = Circuit.from_json(ionq_circuit)
    return circuit.encode(decompose=True)
