// Render the code-native theme glyph at Sailfish's medium-icon density sizes.
// Requires Node.js and sharp; generated PNGs are committed for SDK-only builds.
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
(async () => {
    for (const scale of [1, 1.25, 1.5, 1.75, 2, 2.5, 3]) {
        const label = Number.isInteger(scale) ? scale.toFixed(1) : String(scale);
        const folder = path.join(root, 'assets', 'theme', 'z' + label);
        fs.mkdirSync(folder, {recursive: true});
        const size = Math.round(64 * scale);
        await sharp(path.join(root, 'assets', 'icon-m-quickshare.svg'), {density: 288})
            .resize(size, size).png().toFile(path.join(folder, 'icon-m-quickshare.png'));
    }
})().catch(error => { process.stderr.write(String(error) + '\n'); process.exitCode = 1; });
