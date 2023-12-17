from conversion_lib.qubit import Qubit


class QubitPool:
    def __init__(self) -> None:
        self.next_qubit = 0
        self.max_qubits = 0
        self.freed_qubits = []

    def alloc(self):
        new_qubit = None
        if len(self.freed_qubits) > 0:
            new_qubit = self.freed_qubits.pop(0)._alloc()
        else:
            next_qubit_index = self.next_qubit
            new_qubit = Qubit(next_qubit_index)
            self.next_qubit += 1
        self.max_qubits = max(self.max_qubits, new_qubit.index + 1)
        return new_qubit

    def free(self, qubit: Qubit):
        self.freed_qubits.append(qubit)
