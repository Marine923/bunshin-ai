/**
 * electron-builder afterPack hook.
 *
 * We used to apply an ad-hoc `codesign --force --deep` here. That broke
 * the Electron Framework's existing signature (Team ID mismatch on
 * dyld load — see #signing-notes in docs/TROUBLESHOOTING.md).
 *
 * Without a paid Apple Developer ID we can't properly sign the bundle.
 * For unsigned distribution, the install path simply needs to remove
 * the quarantine attribute (xattr -dr com.apple.quarantine Bunshin.app).
 */
exports.default = async function afterPack(_context) {
  // intentionally no-op for now
};
