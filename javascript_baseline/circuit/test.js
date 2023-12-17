const { Circuit } = require(".");
const fs = require('fs');


function loadCircuit(circuitToLoad) {
    const loadedCircuit = fs.readFileSync(circuitToLoad);
    const parsed = JSON.parse(loadedCircuit);
    const { format, gateset, qubits, circuit } = parsed;
    console.log("Loaded successfully!:", { gateset, qubits, nGates: circuit.length });
    return parsed;
}

function testCircuit(circuitJSON, fileName) {
    const circ = Circuit.fromJSON(circuitJSON);
    const encoded = circ.encode(true);
    let newFileName = fileName.split("\.")
    newFileName = [newFileName[0], "qore.js_baseline"].join(".");
    fs.writeFileSync(newFileName, encoded);
    console.log(`Successfully wrote: ${newFileName}!`);
}

function main() {
    const circuitToLoad = process.argv[2]
    console.log(`Loading ${circuitToLoad}`)
    const circuit = loadCircuit(circuitToLoad)
    testCircuit(circuit, circuitToLoad);
}

main()
