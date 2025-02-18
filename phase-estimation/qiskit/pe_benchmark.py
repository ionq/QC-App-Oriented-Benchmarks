"""
Phase Estimation Benchmark Program - Qiskit
"""

import sys
import time

import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

sys.path[1:1] = ["_common", "_common/qiskit", "quantum-fourier-transform/qiskit"]
sys.path[1:1] = ["../../_common", "../../_common/qiskit", "../../quantum-fourier-transform/qiskit"]
import execute as ex
import metrics as metrics
from qft_benchmark import inv_qft_gate

np.random.seed(0)

verbose = False

# saved subcircuits circuits for printing
QC_ = None
QFTI_ = None
U_ = None

############### Circuit Definition

def PhaseEstimation(num_qubits, theta):
    
    qr = QuantumRegister(num_qubits)
    
    num_counting_qubits = num_qubits - 1 # only 1 state qubit
    
    cr = ClassicalRegister(num_counting_qubits)
    qc = QuantumCircuit(qr, cr)

    # initialize counting qubits in superposition
    for i in range(num_counting_qubits):
        qc.h(qr[i])

    # change to |1> in state qubit, so phase will be applied by cphase gate
    qc.x(num_counting_qubits)

    qc.barrier()

    repeat = 1
    for j in reversed(range(num_counting_qubits)):
        # controlled operation: adds phase exp(i*2*pi*theta*repeat) to the state |1>
        #                       does nothing to state |0>
        cp, _ = CPhase(2*np.pi*theta, repeat)
        qc.append(cp, [j, num_counting_qubits])
        repeat *= 2

    #Define global U operator as the phase operator
    _, U = CPhase(2*np.pi*theta, 1)

    qc.barrier()
    
    # inverse quantum Fourier transform only on counting qubits
    qc.append(inv_qft_gate(num_counting_qubits), qr[:num_counting_qubits])
    
    qc.barrier()
    
    # measure counting qubits
    qc.measure([qr[m] for m in range(num_counting_qubits)], list(range(num_counting_qubits)))

    # save smaller circuit example for display
    global QC_, U_, QFTI_
    if QC_ == None or num_qubits <= 5:
        if num_qubits < 9: QC_ = qc
    if U_ == None or num_qubits <= 5:
        if num_qubits < 9: U_ = U
    if QFTI_ == None or num_qubits <= 5:
        if num_qubits < 9: QFTI_ = inv_qft_gate(num_counting_qubits)
    return qc

#Construct the phase gates and include matching gate representation as readme circuit
def CPhase(angle, exponent):

    qc = QuantumCircuit(1, name=f"U^{exponent}")
    qc.p(angle*exponent, 0)
    phase_gate = qc.to_gate().control(1)

    return phase_gate, qc

# Analyze and print measured results
def analyze_and_print_result(qc, result, num_counting_qubits, theta, num_shots):

    # get results as times a particular theta was measured
    bit_counts = result.get_counts(qc)
    counts = bitstring_to_theta(bit_counts, num_counting_qubits)
    
    if verbose: print(f"For theta value {theta}, measured: {counts}")

    # correct distribution is measuring theta 100% of the time
    correct_dist = {theta: 1.0}

    # calculate expected output histogram
    bit_correct_dist = theta_to_bitstring(theta, num_counting_qubits)

    # generate thermal_dist with amplitudes instead, to be comparable to correct_dist
    bit_thermal_dist = metrics.uniform_dist(num_counting_qubits)
    thermal_dist = bitstring_to_theta(bit_thermal_dist, num_counting_qubits)

    # use our polarization fidelity rescaling
    fidelity = metrics.polarization_fidelity(counts, correct_dist, thermal_dist)
    aq_fidelity = metrics.hellinger_fidelity_with_expected(bit_counts, bit_correct_dist)

    return counts, fidelity, aq_fidelity

def theta_to_bitstring(theta, num_counting_qubits):
    counts = {format( int(theta * (2**num_counting_qubits)), "0"+str(num_counting_qubits)+"b"): 1.0}
    return counts

def bitstring_to_theta(counts, num_counting_qubits):
    theta_counts = {}
    for key in counts.keys():
        r = counts[key]
        theta = int(key,2) / (2**num_counting_qubits)
        if theta not in theta_counts.keys():
            theta_counts[theta] = 0
        theta_counts[theta] += r
    return theta_counts

################ Benchmark Loop

# Execute program with default parameters
def run(min_qubits=3, max_qubits=8, max_circuits=3, num_shots=2500,
        backend_id='qasm_simulator', provider_backend=None,
        hub="ibm-q", group="open", project="main", exec_options=None):

    print("Phase Estimation Benchmark Program - Qiskit")

    num_state_qubits = 1 # default, not exposed to users, cannot be changed in current implementation

    # validate parameters (smallest circuit is 3 qubits)
    num_state_qubits = max(1, num_state_qubits)
    if max_qubits < num_state_qubits + 2:
        print(f"ERROR: PE Benchmark needs at least {num_state_qubits + 2} qubits to run")
        return
    min_qubits = max(max(3, min_qubits), num_state_qubits + 2)
    #print(f"min, max, state = {min_qubits} {max_qubits} {num_state_qubits}")

    # Initialize metrics module
    metrics.init_metrics()

    # Define custom result handler
    def execution_handler(qc, result, num_qubits, theta, num_shots):

        # determine fidelity of result set
        num_counting_qubits = int(num_qubits) - 1
        counts, fidelity, aq_fidelity = analyze_and_print_result(qc, result, num_counting_qubits, float(theta), num_shots)
        metrics.store_metric(num_qubits, theta, 'fidelity', fidelity)
        metrics.store_metric(num_qubits, theta, 'aq_fidelity', aq_fidelity)

    # Initialize execution module using the execution result handler above and specified backend_id
    ex.init_execution(execution_handler)
    ex.set_execution_target(backend_id, provider_backend=provider_backend,
            hub=hub, group=group, project=project, exec_options=exec_options)

    # Execute Benchmark Program N times for multiple circuit sizes
    # Accumulate metrics asynchronously as circuits complete
    for num_qubits in range(min_qubits, max_qubits + 1):
        
        # reset random seed
        np.random.seed(0)

        # as circuit width grows, the number of counting qubits is increased
        num_counting_qubits = num_qubits - num_state_qubits - 1

        # determine number of circuits to execute for this group
        num_circuits = min(2 ** (num_counting_qubits), max_circuits)
        
        print(f"************\nExecuting [{num_circuits}] circuits with num_qubits = {num_qubits}")
        
        # determine range of secret strings to loop over
        if 2**(num_counting_qubits) <= max_circuits:
            theta_range = [i/(2**(num_counting_qubits)) for i in list(range(num_circuits))]
        else:
            theta_range = [i/(2**(num_counting_qubits)) for i in np.random.choice(2**(num_counting_qubits), num_circuits, False)]

        # loop over limited # of random theta choices
        for theta in theta_range:
            # create the circuit for given qubit size and theta, store time metric
            ts = time.time()

            qc = PhaseEstimation(num_qubits, theta)
            metrics.store_metric(num_qubits, theta, 'create_time', time.time() - ts)

            # collapse the 3 sub-circuit levels used in this benchmark (for qiskit)
            qc2 = qc.decompose().decompose().decompose()
            
            # submit circuit for execution on target (simulator, cloud simulator, or hardware)
            ex.submit_circuit(qc2, num_qubits, theta, num_shots)

        # Wait for some active circuits to complete; report metrics when groups complete
        ex.throttle_execution(metrics.finalize_group)

    # Wait for all active circuits to complete; report metrics when groups complete
    ex.finalize_execution(metrics.finalize_group)

    # print a sample circuit
    print("Sample Circuit:"); print(QC_ if QC_ != None else "  ... too large!")
    print("\nPhase Operator 'U' = "); print(U_ if U_ != None else "  ... too large!")
    print("\nInverse QFT Circuit ="); print(QFTI_ if QFTI_ != None else "  ... too large!")

    # Plot metrics for all circuit sizes
    metrics.plot_metrics_aq("Benchmark Results - Phase Estimation - Qiskit")


# if main, execute method
if __name__ == '__main__': run()
