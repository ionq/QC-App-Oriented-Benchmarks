import json

from typing import List
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union
from typing import Generator
from typing import Tuple
from typing import Callable

from conversion_lib.gate import Gate
from conversion_lib.qubit_pool import QubitPool
from conversion_lib.utils import is_number


def getitems(*items_to_get: str) -> Callable[[Any], Tuple[Any, ...]]:
    getters = ()
    for item in items_to_get:

        def getter_factory(item_spec):
            def getter(obj):
                nonlocal item_spec
                return obj.get(item_spec)

            return getter

        getters += (getter_factory(item),)

    def multigetter(obj):
        nonlocal getters
        return tuple([getter(obj) for getter in getters])

    return multigetter


def get_gate_type(op):
    return op["gate"].type.lower()


def gen_controls(gate: Gate) -> str:
    if len(gate.controls) == 0:
        return ""
    controls = [str(control) for control in gate.controls]
    controls_str = ",".join(controls)
    return f"[{controls_str}]"


def serialize_op(op: Dict[Any, Any]) -> str:
    gate = op.get("gate")
    if op.get("call") is not None:
        args = []
        qubits = op.get("qubits")
        params = op.get("params")
        if qubits is not None:
            for key in qubits:
                qubit_list_str = ",".join([q.index for q in qubits[key]])
                args.append(
                    f"{key}=[{qubit_list_str}]",
                )
        if params is not None:
            for key in params:
                args.append(f"{key}={params[key]}")
        args_str = " ".join(args)
        call_str = str(op["call"])
        return f"call {call_str} {args_str}"
    elif op.get("label") is not None:
        label = op.get("label")
        return f"label {label}"
    elif op.get("sample") is not None:
        sample = op.get("sample")
        return f"sample {sample}"
    elif gate is not None:
        gate_type = get_gate_type(op)
        targets = [str(target) for target in gate.targets]
        targets_str = ",".join(targets)
        gate_str = f"op {gate_type} [{targets_str}] {gen_controls(gate)}"
        if gate.has_gate_angle():
            rotation = gate.rotation
            gate_str += f" {rotation}"
        return gate_str
    else:
        raise TypeError(f"unknown op {repr(op)}")


class ZZGateDecomposer:
    """Legacy behavior - decomposes 2q gates into the zz basis. A good candidate for rolling into
    chiron eventually
    """

    DECOMPOSABLE_GATES = set(["xx", "yy", "zz"])
    DIAGONAL_DECOMPOSITION = set(["xx", "yy"])
    OFF_DIAGONAL_DECOMPOSITION = set(["yy"])

    def _off_diagonal_decomposition(
        self, op
    ) -> Tuple[Optional[List[Dict[Any, Any]]], Optional[List[Dict[Any, Any]]]]:
        if get_gate_type(op) not in ZZGateDecomposer.OFF_DIAGONAL_DECOMPOSITION:
            return None, None

        def si_compensate(target):
            nonlocal op
            return {"gate": Gate("si", [target], op.gate.controls)}

        def s_compensate(target):
            nonlocal op
            return {"gate": Gate("s", [target], op.gate.controls)}

        targets = op["gate"]["targets"]
        assert len(targets) == 2
        return [si_compensate(target) for target in targets], [
            s_compensate(target) for target in targets
        ]

    def _diagonal_decomposition(
        self, op
    ) -> Tuple[Optional[List[Dict[Any, Any]]], Optional[List[Dict[Any, Any]]]]:
        if get_gate_type(op) not in ZZGateDecomposer.DIAGONAL_DECOMPOSITION:
            return None, None

        def h_compensate(target):
            nonlocal op
            return {
                "gate": Gate("h", [target], op.gate.controls),
            }

        targets = op["gate"]["targets"]
        assert len(targets) == 2
        return [h_compensate(target) for target in targets], [
            h_compensate(target) for target in targets
        ]

    def _core_zz_decomposition(
        self, op
    ) -> Tuple[Optional[List[Dict[Any, Any]]], Optional[List[Dict[Any, Any]]]]:
        apply = [
            {
                "gate": Gate(
                    "z",
                    [op.gate.targets[1]],
                    [*op.gate.controls, op.gate.targets[0]],
                    -2 * op.gate.rotation,
                )
            },
            {
                "gate": Gate(
                    "rz", [op.gate.targets[1]], op.gate.controls, op.gate.rotation
                ),
            },
            {
                "gate": Gate(
                    "rz", [op.gate.targets[0]], op.gate.controls, op.gate.rotation
                ),
            },
        ]
        return apply, None

    def _decompose_gate(self, op) -> Optional[List[str]]:
        """
        Decomposes 2q gates into the zz basis.
        Returns None if the gate was not actually decomposes - otherwise
        it returns the list of decomposed ops.
        """
        gate_type = get_gate_type(op)

        ops = []

        if gate_type not in ZZGateDecomposer.DECOMPOSABLE_GATES:
            return None

        apply_forward_queue = []
        apply_after_stack = []
        for before, after in [
            self._off_diagonal_decomposition(op),
            self._diagonal_decomposition(op),
            self._core_zz_decomposition(op),
        ]:
            if before is not None:
                apply_forward_queue.append(before)
            if after is not None:
                apply_after_stack.append(after)
        while len(apply_forward_queue) > 0:
            ops += apply_forward_queue.pop(0)
        while len(apply_after_stack) > 0:
            ops += apply_after_stack.pop()
        return [serialize_op(op) for op in ops]

    def __call__(self, op) -> Optional[List[str]]:
        return self._decompose_gate(op)


def flat_ops(
    ls: List[Union[List[Dict[Any, Any]], Dict[Any, Any]]]
) -> Generator[Dict[Any, Any], None, None]:
    flat_map = [ops if isinstance(ops, list) else [ops] for ops in ls]
    for ops in flat_map:
        yield from ops


class Circuit:
    def __init__(
        self,
        pool: Optional[QubitPool] = None,
        ops: Optional[List[Any]] = None,
        options: Optional[Dict[Any, Any]] = None,
    ) -> None:
        self.pool = pool or QubitPool()
        self.ops = ops or []
        self.options = options or {}
        self.sets = {}  # named qubit sets
        self.params = {}  # named parameters
        self.shot_count = 1000  # default number of shots for execution
        self.qubits = []

    def max_qubits(self):
        return self.pool.max_qubits

    """
    This class represents the series of operations necessary to
    execute a quantum circuit.  Qubit instances reference a target
    circuit making their gate calling convention more natural.
    """

    @classmethod
    def from_json(cls, json_input: Optional[Union[str, Dict[Any, Any]]]):
        c = cls()

        if json_input is None:
            return c  # return empty circuit in the base case

        desc = json_input if isinstance(json_input, dict) else json.loads(json_input)

        if desc["qubits"] is not None:
            c.alloc(desc["qubits"])

        if isinstance(desc["circuit"], list):
            # supporting nested op groups
            for op in flat_ops(desc["circuit"]):
                if op["gate"] is not None:
                    gate, target, targets, control, controls, rotation = getitems(
                        "gate", "target", "targets", "control", "controls", "rotation"
                    )(op)
                    if c.qubits[0] is None:
                        raise TypeError("no qubits allocated")
                    if is_number(targets):
                        targets = [targets]
                    if is_number(controls):
                        controls = [controls]

                    # FIXME: CNOT should probably be a first class type?
                    if gate.upper() == "CNOT":
                        gate = "NOT"
                        [targets, controls] = [controls, targets]
                    gate_target = (
                        [c.qubits[target]]
                        if target is not None
                        else [c.qubits[qubit_index] for qubit_index in targets]
                    )
                    gate_control = None
                    if controls is not None:
                        gate_control = (
                            [c.qubits[control]]
                            if control is not None
                            else [c.qubits[qubit_index] for qubit_index in controls]
                        )
                    c._add_gate(gate.upper(), gate_target, gate_control, rotation)
        return c

    def _alloc(self):
        new_qubit = self.pool.alloc()
        self.qubits.append(new_qubit)

    def alloc(self, n):
        n = max(n or 1, 1)
        return self.allocate_qubits(n)

    def allocate_qubits(self, count):
        self._add_op(
            {
                "alloc": count,
            }
        )
        return [self._alloc() for _ in range(count)]

    @classmethod
    def decompose_gate(cls, op, out):
        decomposer = ZZGateDecomposer()
        decomposed_ops = decomposer(op)
        if decomposed_ops is not None:
            for decomposed_op in decomposed_ops:
                out.append(decomposed_op)
            return len(decomposed_ops)
        else:
            return 0

    def encode(self, decompose=True):
        out = [f"alloc [{self.max_qubits()}]"]
        count = 2  # alloc + free
        for op in self.ops:
            if op.get("call") is not None:
                out.append(serialize_op(op))
            elif op.get("label") is not None:
                out.append(serialize_op(op))
                count += 1
            elif op.get("sample") is not None:
                out.append(serialize_op(op))
                count += 1
            elif op.get("gate") is not None:
                if decompose:
                    n_decomposed = Circuit.decompose_gate(op, out)
                    if n_decomposed > 0:
                        count += n_decomposed
                        continue
                out.append(serialize_op(op))
                count += 1
        out.append("free")
        out = [
            f"// max qubit {self.max_qubits()}",
            f"// ops count {count}",
            f"// shots {self.shot_count}",
        ] + out
        return "\n".join(out) + "\n"

    def _add_op(self, op):
        self.ops.append(op)

    def _add_gate(self, gate_type, targets, controls, rotation):
        self._add_op({"gate": Gate(gate_type, targets, controls, rotation)})
