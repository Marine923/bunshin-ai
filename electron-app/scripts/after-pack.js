/**
 * electron-builder afterPack hook — apply ad-hoc signature so the .app
 * is internally consistent for macOS Sequoia (which is stricter about
 * unsigned binaries) without needing a paid Developer ID.
 */
const { execSync } = require('node:child_process');
const path = require('node:path');

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  console.log(`▸ Applying ad-hoc signature to ${appPath}`);
  try {
    execSync(
      `codesign --force --deep --sign - --options runtime "${appPath}"`,
      { stdio: 'inherit' }
    );
    console.log('✓ Ad-hoc signed');
  } catch (e) {
    console.warn('⚠ Ad-hoc signing failed (will still build):', e.message);
  }
};
