from typing import List
from typing import Any
from typing import Set
from typing import Optional

from enum import Enum
import math

from conversion_lib.qubit import Qubit
from conversion_lib.utils import is_number


class GATE_TYPES(Enum):
    NOT = "NOT"
    H = "H"
    X = "X"
    Y = "Y"
    Z = "Z"
    RX = "RX"
    RY = "RY"
    RZ = "RZ"
    SWAP = "SWAP"
    S = "S"
    SI = "SI"
    T = "T"
    TI = "TI"
    V = "V"
    VI = "VI"
    R2 = "R2"
    R4 = "R4"
    R8 = "R8"
    XX = "XX"
    YY = "YY"
    ZZ = "ZZ"


BINARY_GATES = {"swap", "xx", "yy", "zz"}
HAS_GATE_ANGLE = {"x", "y", "z", "rx", "ry", "rz", "xx", "yy", "zz"}


class Gate:
    """
    this class stores the gate type, target qubits, control qubits
    and rotation necessary to perform a gate operation.  it is decoded
    at execution time by the system class.
    """

    def __init__(
        self,
        gate_type: str,
        targets: List[Qubit],
        controls: List[Qubit] = [],
        rotation: Optional[Any] = None,
    ):
        if controls is None:
            controls = []
        self.type = gate_type.lower()
        self.count = len(targets)
        self.count += len(controls)

        is_binary_gate = self.type in BINARY_GATES

        if is_binary_gate and len(targets) != 2:
            raise ValueError(f"{self.type} gate requires exactly two target qubits")

        if not is_binary_gate and len(targets) != 1:
            raise ValueError("gate requires only one target qubit")

        seen_indices: Set[int] = set()
        for target in targets:
            assert isinstance(target, Qubit)
            if target.index in seen_indices:
                raise ValueError(f"duplicate qubit: {target.index}")
            seen_indices.add(target.index)

        for target in controls:
            assert isinstance(target, Qubit)
            if target.index in seen_indices:
                raise ValueError(f"duplicate qubit: {target.index}")
            seen_indices.add(target.index)

        self.targets = self.resolve(targets)
        self.controls = self.resolve(controls)

        if self.has_gate_angle():
            self.rotation = rotation if is_number(rotation) else math.pi
        else:
            if rotation is not None:
                raise ValueError("rotation angle cannot be used with {self.type} gate")

    def resolve(self, qubits: List[Qubit]):
        """
        turn qubit or qubit array into an array of their indices
        """
        indices = [qubit.index for qubit in qubits]
        return indices

    def has_gate_angle(self) -> bool:
        return self.type in HAS_GATE_ANGLE
