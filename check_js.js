const fs = require('fs');
const html = fs.readFileSync('C:/Users/WU/Desktop/lexis/templates/vocab/settings.html', 'utf8');

// Extract the JS between <script> and </script> tags near the end
const startTag = html.indexOf('<script>\n(function()');
const endTag = html.indexOf('</script>', startTag);

if (startTag === -1 || endTag === -1) {
  console.log('Script block not found');
  process.exit(1);
}

let js = html.substring(startTag + 8, endTag); // skip <script>

// Replace Django template tags with placeholders
js = js.replace(/\{%.*?%\}/g, '""');
js = js.replace(/\{\{.*?\}\}/g, '""');

const vm = require('vm');
try {
  new vm.Script(js, { filename: 'settings.html' });
  console.log('JS SYNTAX: OK - No errors found');
} catch(e) {
  console.log('JS SYNTAX ERROR:', e.message);
  if (e.stack) {
    const match = e.stack.match(/settings\.html:(\d+)/);
    if (match) {
      const lineNum = parseInt(match[1]);
      const lines = js.split('\n');
      console.log('Error around line', lineNum, 'of the JS string:');
      for (let i = Math.max(0, lineNum - 5); i < Math.min(lines.length, lineNum + 5); i++) {
        console.log(`${i+1}: ${lines[i]}`);
      }
    }
  }
}
