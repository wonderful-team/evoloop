// Exclude HarmonyOS fork packages from iOS/Android builds
const fs = require('fs');
const path = require('path');

// Scan node_modules/@react-native-ohos for packages to exclude
const ohosDir = path.resolve(__dirname, 'node_modules/@react-native-ohos');
const ohosTplDir = path.resolve(__dirname, 'node_modules/@react-native-oh-tpl');

const dependencies = {};

function excludeDir(dir, prefix) {
  if (!fs.existsSync(dir)) return;
  fs.readdirSync(dir).forEach(name => {
    if (name.startsWith('.')) return;
    const pkgName = `${prefix}/${name}`;
    dependencies[pkgName] = {
      platforms: {
        ios: null,
        android: null,
      },
    };
  });
}

excludeDir(ohosDir, '@react-native-ohos');
excludeDir(ohosTplDir, '@react-native-oh-tpl');

module.exports = {
  dependencies,
};
