const fs = require('fs');
const path = require('path');

// Force load evoloop/.env (or ENVFILE) into process.env to prevent react-native-dotenv from overriding it with .env.local
try {
  const envFile = process.env.ENVFILE || '../.env';
  const envPath = path.resolve(__dirname, envFile);
  if (fs.existsSync(envPath)) {
    const dotenv = require('dotenv');
    const envConfig = dotenv.parse(fs.readFileSync(envPath));
    for (const k in envConfig) {
      process.env[k] = envConfig[k];
    }
  }
} catch (e) {
  console.error('Failed to pre-load env in babel.config.js:', e);
}

module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    [
      'module-resolver',
      {
        root: ['./src'],
        alias: {
          '@': './src',
        },
      },
    ],
    'react-native-reanimated/plugin',
    [
      'module:react-native-dotenv',
      {
        moduleName: '@env',
        path: process.env.ENVFILE || path.resolve(__dirname, '../.env'),
        blocklist: null,
        allowlist: null,
        safe: false,
        allowUndefined: true,
        verbose: false,
      },
    ],
  ],
};
