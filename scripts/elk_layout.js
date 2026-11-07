// Reads an ELK graph (JSON) on stdin, writes the laid-out graph (JSON) on stdout.
// Uses the vendored elk.bundled.js so no npm install is needed.
const path = require('path');
const ELK = require(path.join(__dirname, 'vendor', 'elk.bundled.js'));

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  let graph;
  try {
    graph = JSON.parse(input);
  } catch (e) {
    process.stderr.write('elk_layout: bad JSON input: ' + e.message + '\n');
    process.exit(2);
  }
  new ELK().layout(graph)
    .then((out) => { process.stdout.write(JSON.stringify(out)); })
    .catch((e) => {
      process.stderr.write('elk_layout: layout failed: ' + (e && e.message ? e.message : e) + '\n');
      process.exit(3);
    });
});
