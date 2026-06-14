#!/usr/bin/env node
/**
 * Builds the macOS .icns and Linux/Windows PNGs from build/icon.svg.
 *
 * Requires `sharp` (devDependency). On macOS we then call `iconutil`
 * to produce the .icns bundle from an .iconset directory.
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const sharp = require('sharp');

const BUILD_DIR = path.join(__dirname, '..', 'build');
const SVG = path.join(BUILD_DIR, 'icon.svg');
const ICONSET_DIR = path.join(BUILD_DIR, 'icon.iconset');

// macOS icon size table — required by iconutil.
const ICONSET_SIZES = [
  { name: 'icon_16x16.png', size: 16 },
  { name: 'icon_16x16@2x.png', size: 32 },
  { name: 'icon_32x32.png', size: 32 },
  { name: 'icon_32x32@2x.png', size: 64 },
  { name: 'icon_128x128.png', size: 128 },
  { name: 'icon_128x128@2x.png', size: 256 },
  { name: 'icon_256x256.png', size: 256 },
  { name: 'icon_256x256@2x.png', size: 512 },
  { name: 'icon_512x512.png', size: 512 },
  { name: 'icon_512x512@2x.png', size: 1024 },
];

async function main() {
  console.log('▸ Reading SVG:', SVG);
  const svgBuffer = await fs.readFile(SVG);

  // Clean & recreate iconset dir
  await fs.rm(ICONSET_DIR, { recursive: true, force: true });
  await fs.mkdir(ICONSET_DIR, { recursive: true });

  console.log('▸ Rendering PNGs at all required sizes...');
  for (const { name, size } of ICONSET_SIZES) {
    const out = path.join(ICONSET_DIR, name);
    await sharp(svgBuffer, { density: 384 })
      .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .png()
      .toFile(out);
    console.log(`   ✓ ${name} (${size}×${size})`);
  }

  // 1024×1024 standalone PNG for Linux / Windows / web
  const pngOut = path.join(BUILD_DIR, 'icon.png');
  await sharp(svgBuffer, { density: 384 })
    .resize(1024, 1024)
    .png()
    .toFile(pngOut);
  console.log(`   ✓ icon.png (1024×1024)`);

  // macOS only: build .icns
  if (process.platform === 'darwin') {
    console.log('▸ Building .icns via iconutil...');
    const icnsOut = path.join(BUILD_DIR, 'icon.icns');
    execFileSync('iconutil', ['-c', 'icns', '-o', icnsOut, ICONSET_DIR], {
      stdio: 'inherit',
    });
    console.log(`   ✓ icon.icns`);
  } else {
    console.log('▸ Skipping .icns build (not on macOS)');
  }

  console.log('\n✓ All icons built into build/');
}

main().catch((err) => {
  console.error('✗ Icon build failed:', err);
  process.exit(1);
});
