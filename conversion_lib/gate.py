from dataclasses import dataclass

from typing import List
from typing import Any
from typing import Optional


# Gate(gate_type, targets, controls, rotation)
@dataclass
class Gate:
    gate_type: str
    targets: List[Any]
    controls: List[Any]
    rotation: List[Any]
    controlsOC: Optional[List[Any]] = None
